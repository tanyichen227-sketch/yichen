import asyncio
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / 'local-KLB-files'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def get_request_data(request: Request):
    try:
        content_type = request.headers.get('content-type', '')
        if 'application/json' in content_type:
            return await request.json()
        form = await request.form()
        return dict(form)
    except Exception:
        return {}


def get_safe_dir(kid: str):
    kid = str(kid).strip()
    exact_path = UPLOAD_DIR / kid
    if exact_path.is_dir():
        return str(exact_path), kid

    for entry in UPLOAD_DIR.iterdir():
        if entry.is_dir() and entry.name.lower() == kid.lower():
            return str(entry), entry.name

    return str(exact_path), kid


def generate_doc_info(file_name: str, file_path: str, real_kid: str):
    path = Path(file_path)
    mtime = path.stat().st_mtime if path.exists() else datetime.now().timestamp()
    dt_str = datetime.fromtimestamp(mtime).isoformat()

    ext = path.suffix[1:].lower() if path.suffix else 'txt'
    return {
        'id': file_name,
        'name': file_name,
        'fileType': ext or 'txt',
        'chunks': 1,
        'uploadDate': dt_str,
        'slicingMethod': '自动切片',
        'enabled': True,
        'status': 'success',
        'kbId': real_kid,
    }


@router.get('/api/documents-list/{KLB_id}')
@router.get('/api/documents-list/{KLB_id}/')
async def get_docs_list(KLB_id: str):
    target_dir, real_kid = get_safe_dir(KLB_id)
    docs = []
    if os.path.exists(target_dir):
        for name in sorted(os.listdir(target_dir)):
            if name in {'knowledge_data.json', 'vectorstore', 'native_vectorstore'} or name.startswith('.'):
                continue
            file_path = os.path.join(target_dir, name)
            if os.path.isfile(file_path):
                docs.append(generate_doc_info(name, file_path, real_kid))
    return docs


@router.post('/api/RAG/ingest-legacy')
@router.post('/api/RAG/ingest-legacy/')
async def rag_ingest(request: Request):
    data = await get_request_data(request)
    docs_dir = data.get('docs_dir', '')
    kid = docs_dir.split('/')[-1] if docs_dir else (data.get('KLB_id') or '1')
    target_dir, real_kid = get_safe_dir(str(kid))

    async def generate_stream():
        yield f'data: [system] Preparing vectorization for knowledge base [{real_kid}]...\n\n'
        await asyncio.sleep(0.2)
        try:
            from document_processing.vectorize_task import _do_vectorize

            yield 'data: [system] Reading documents and running vectorization...\n\n'
            await asyncio.to_thread(_do_vectorize, real_kid, target_dir)
            yield 'data: {"message":"legacy ingest finished","status":"success"}\n\n'
        except Exception as exc:
            yield f'data: [error] Vectorization failed: {exc}\n\n'

    return StreamingResponse(generate_stream(), media_type='text/event-stream')


@router.post('/api/update-document-status')
@router.post('/api/update-document-status/')
async def update_doc_status(request: Request):
    return {'code': 200, 'status': 'success', 'message': '状态更新成功'}


@router.post('/api/delete-documents')
@router.post('/api/delete-documents/')
async def delete_docs(request: Request):
    data = await get_request_data(request)
    doc_ids = data.get('documentIds', [])
    kb_id = request.query_params.get('KLB_id', '1')
    target_dir, _ = get_safe_dir(str(kb_id))
    if os.path.exists(target_dir):
        for doc_id in doc_ids:
            file_path = os.path.join(target_dir, str(doc_id))
            if os.path.exists(file_path):
                os.remove(file_path)
    return {'code': 200, 'status': 'success', 'message': '删除成功'}


@router.get('/api/get-knowledge-item/{KLB_id}')
async def get_kb_item(KLB_id: str):
    _, real_kid = get_safe_dir(KLB_id)
    return {
        'code': 200,
        'data': {
            'id': real_kid,
            'title': real_kid,
            'name': real_kid,
            'description': '本地知识库项目',
            'owner': 'tanyi',
            'create_time': datetime.now().strftime('%Y-%m-%d'),
        },
    }


@router.post('/api/upload-chunk')
async def upload_chunk(request: Request):
    form = await request.form()
    chunk = form.get('chunk')
    uid = form.get('uploadId') or form.get('fileHash')
    idx = form.get('chunkIndex')

    if chunk is None:
        raise HTTPException(status_code=400, detail='missing field: chunk')
    if uid is None or str(uid).strip() == '':
        raise HTTPException(status_code=400, detail='missing field: uploadId/fileHash')
    if idx is None or str(idx).strip() == '':
        raise HTTPException(status_code=400, detail='missing field: chunkIndex')

    temp_dir = UPLOAD_DIR / 'temp' / str(uid)
    temp_dir.mkdir(parents=True, exist_ok=True)
    with (temp_dir / str(idx)).open('wb') as f:
        f.write(await chunk.read())

    return {'status': 'success', 'code': 200, 'uploadId': str(uid)}


@router.post('/api/upload-complete')
async def upload_complete(request: Request):
    data = await get_request_data(request)
    uid = data.get('uploadId') or data.get('fileHash')
    file_name = data.get('fileName') or data.get('filename') or data.get('name')
    kid = data.get('KLB_id') or data.get('kb_id') or '1'

    if uid is None or str(uid).strip() == '':
        raise HTTPException(status_code=400, detail='missing field: uploadId/fileHash')
    if file_name is None or str(file_name).strip() == '':
        raise HTTPException(status_code=400, detail='missing field: fileName/filename/name')

    file_name = os.path.basename(str(file_name).strip())
    if not os.path.splitext(file_name)[1]:
        file_name = f'{file_name}.txt'

    _, real_kid = get_safe_dir(str(kid))
    final_dir = UPLOAD_DIR / real_kid
    final_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = UPLOAD_DIR / 'temp' / str(uid)
    if not temp_dir.exists():
        raise HTTPException(status_code=400, detail=f'temp chunks not found for uploadId={uid}')

    chunks = sorted(int(name) for name in os.listdir(temp_dir) if name.isdigit())
    if not chunks:
        raise HTTPException(status_code=400, detail=f'no chunk files found for uploadId={uid}')

    final_name = f"{datetime.now().strftime('%H%M%S')}-{file_name}"
    final_path = final_dir / final_name
    with final_path.open('wb') as outfile:
        for index in chunks:
            with (temp_dir / str(index)).open('rb') as infile:
                outfile.write(infile.read())

    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    return generate_doc_info(final_name, str(final_path), real_kid)
