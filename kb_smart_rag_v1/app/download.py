from modelscope.hub.snapshot_download import snapshot_download
# 这会将模型下载到你当前系统的默认缓存目录
model_dir = snapshot_download('sentence-transformers/all-MiniLM-L6-v2')
print(f"模型下载成功，路径为: {model_dir}")