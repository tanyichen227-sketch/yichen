<template>
  <div class="graph-container flex flex-col gap-3">
    <div class="toolbar flex flex-wrap items-center gap-2">
      <button
        class="btn btn-primary"
        :disabled="isLoading"
        @click="fetchMergedGraph"
      >
        <span v-if="isLoading && loadingType === 'merged'">加载中...</span>
        <span v-else>加载全图</span>
      </button>

      <button
        class="btn btn-success"
        :disabled="isLoading"
        @click="fetchGraphData"
      >
        <span v-if="isLoading && loadingType === 'generate'">生成中...</span>
        <span v-else>生成图谱</span>
      </button>

      <div class="search-wrap">
        <input
          v-model="searchKeyword"
          class="search-input"
          placeholder="搜索节点"
          @keyup.enter="searchNodes"
        />
        <button
          class="btn btn-search"
          :disabled="isLoading || !searchKeyword.trim()"
          @click="searchNodes"
        >
          搜索
        </button>
        <button
          v-if="isSearchMode"
          class="btn btn-clear"
          @click="clearSearch"
        >
          清除
        </button>
      </div>

      <button
        class="btn btn-stats"
        @click="toggleStats"
      >
        统计
      </button>

      <div
        v-if="showStats && graphStats"
        class="stats-panel"
      >
        <div class="stats-header">
          <span>图谱统计</span>
          <button class="close-btn" @click="showStats = false">关闭</button>
        </div>
        <div class="stats-line">节点总数: {{ graphStats.node_count }}</div>
        <div class="stats-line">边总数: {{ graphStats.edge_count }}</div>
        <div class="stats-line">孤立节点: {{ graphStats.isolated_node_count }}</div>
        <div v-if="graphStats.type_distribution" class="stats-types">
          <div class="stats-types-title">实体类型分布</div>
          <div
            v-for="(count, type) in graphStats.type_distribution"
            :key="type"
            class="stats-line stats-type-item"
          >
            <span>{{ type }}</span>
            <span>{{ count }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="errorMessage" class="error-box">
      {{ errorMessage }}
    </div>

    <div v-if="renderNotice" class="notice-box">
      {{ renderNotice }}
    </div>

    <div v-if="isSearchMode" class="search-hint">
      搜索“{{ lastKeyword }}”，命中 {{ searchMatchCount }} 个相关节点
    </div>

    <div class="graph-stage">
      <div ref="graphContainerRef" class="graph-canvas"></div>
      <div v-if="!hasRenderedGraph" class="graph-placeholder">
        点击“加载全图”或“生成图谱”
      </div>

      <transition name="slide">
        <div v-if="selectedNode" class="node-detail">
          <div class="node-detail-header">
            <span>节点详情</span>
            <button class="close-btn" @click="clearSelection">关闭</button>
          </div>
          <div class="node-detail-line">ID: {{ selectedNode.id }}</div>
          <div class="node-detail-line">名称: {{ selectedNode.label }}</div>
          <div class="node-detail-line">
            类型:
            <span class="type-tag" :style="{ backgroundColor: getNodeColor(selectedNode.type || '默认') }">
              {{ selectedNode.type || '默认' }}
            </span>
          </div>
          <div class="node-detail-line">出度: {{ getNodeDegree(selectedNode.id, 'out') }}</div>
          <div class="node-detail-line">入度: {{ getNodeDegree(selectedNode.id, 'in') }}</div>
          <div class="relation-block">
            <div class="relation-title">相关关系</div>
            <div
              v-for="rel in getNodeRelations(selectedNode.id)"
              :key="rel.key"
              class="relation-item"
            >
              <span v-if="rel.direction === 'out'">→ {{ rel.target }}</span>
              <span v-else>← {{ rel.source }}</span>
              <span class="relation-label">({{ rel.label }})</span>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as d3 from 'd3'
import API_ENDPOINTS from '@/utils/apiConfig'

interface GraphNode {
  id: string
  label?: string
  name?: string
  type?: string
}

interface GraphEdge {
  source: string
  target: string
  label?: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

interface GraphStats {
  node_count: number
  edge_count: number
  isolated_node_count: number
  type_distribution?: Record<string, number>
}

interface GraphMessageResponse extends Partial<GraphData> {
  message?: string
  detail?: string
  matched_count?: number
}

interface GeneratedGraphItem {
  message?: string
  graph_data?: GraphData
}

interface GraphNodeDatum extends d3.SimulationNodeDatum {
  id: string
  label: string
  type: string
  color: string
  degree: number
  size: number
}

interface GraphLinkDatum extends d3.SimulationLinkDatum<GraphNodeDatum> {
  source: string | GraphNodeDatum
  target: string | GraphNodeDatum
  label: string
}

const props = defineProps<{ kbId?: string }>()
const route = useRoute()

const graphContainerRef = ref<HTMLDivElement | null>(null)

const isLoading = ref(false)
const loadingType = ref<'generate' | 'merged' | 'search' | ''>('')
const errorMessage = ref('')
const renderNotice = ref('')

const searchKeyword = ref('')
const lastKeyword = ref('')
const isSearchMode = ref(false)
const searchMatchCount = ref(0)

const selectedNode = ref<GraphNode | null>(null)
const showStats = ref(false)
const graphStats = ref<GraphStats | null>(null)

const hasRenderedGraph = ref(false)
const currentGraphData = ref<GraphData | null>(null)

const MAX_RENDER_NODES = 260
const MAX_RENDER_EDGES = 420

const NODE_COLORS: Record<string, string> = {
  人物: '#ff6b6b',
  PERSON: '#ff6b6b',
  门派: '#f59e0b',
  组织: '#45b7d1',
  ORGANIZATION: '#45b7d1',
  地点: '#4ecdc4',
  LOCATION: '#4ecdc4',
  事件: '#06d6a0',
  EVENT: '#06d6a0',
  概念: '#ffd166',
  CONCEPT: '#ffd166',
  时间: '#a78bfa',
  TIME: '#a78bfa',
  默认: '#90d8ff'
}

let svg: d3.Selection<SVGSVGElement, unknown, null, undefined> | null = null
let viewport: d3.Selection<SVGGElement, unknown, null, undefined> | null = null
let simulation: d3.Simulation<GraphNodeDatum, GraphLinkDatum> | null = null
let zoomBehavior: d3.ZoomBehavior<SVGSVGElement, unknown> | null = null
let applySelectionRef: ((nodeId: string | null) => void) | null = null

let currentNodes: GraphNode[] = []
let currentEdges: GraphEdge[] = []

const resolveKbId = (): string => {
  const propValue = props.kbId?.trim()
  if (propValue) return propValue
  const routeValue = String(route.params.id || '').trim()
  return routeValue
}

const getNodeColor = (type: string): string => NODE_COLORS[type] || NODE_COLORS.默认

const getResponseMessage = async (res: Response): Promise<string> => {
  try {
    const payload = (await res.clone().json()) as GraphMessageResponse
    return payload.detail || payload.message || res.statusText
  } catch {
    return res.statusText
  }
}

const mergeGraphData = (graphList: GraphData[]): GraphData => {
  const nodes = new Map<string, GraphNode>()
  const edges = new Map<string, GraphEdge>()

  graphList.forEach(graphItem => {
    graphItem.nodes?.forEach(node => {
      if (node?.id && !nodes.has(node.id)) {
        nodes.set(node.id, node)
      }
    })

    graphItem.edges?.forEach(edge => {
      if (!edge?.source || !edge?.target) return
      const key = `${edge.source}::${edge.target}::${edge.label || ''}`
      if (!edges.has(key)) {
        edges.set(key, edge)
      }
    })
  })

  return {
    nodes: Array.from(nodes.values()),
    edges: Array.from(edges.values())
  }
}

const normalizeGraphData = (graphData: GraphData): GraphData => {
  const nodeMap = new Map<string, GraphNode>()
  const edgeMap = new Map<string, GraphEdge>()

  graphData.nodes.forEach(node => {
    if (!node?.id) return
    const label = (node.label || node.name || node.id).trim()
    nodeMap.set(node.id, {
      id: node.id,
      label: label || node.id,
      type: node.type || '默认'
    })
  })

  graphData.edges.forEach(edge => {
    if (!edge?.source || !edge?.target) return
    if (!nodeMap.has(edge.source) || !nodeMap.has(edge.target)) return
    const key = `${edge.source}::${edge.target}::${edge.label || ''}`
    if (!edgeMap.has(key)) {
      edgeMap.set(key, {
        source: edge.source,
        target: edge.target,
        label: edge.label || '关联'
      })
    }
  })

  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values())
  }
}

const trimGraphForDisplay = (graphData: GraphData): GraphData => {
  renderNotice.value = ''

  if (
    graphData.nodes.length <= MAX_RENDER_NODES &&
    graphData.edges.length <= MAX_RENDER_EDGES
  ) {
    return graphData
  }

  const degreeMap = new Map<string, number>()
  graphData.nodes.forEach(node => degreeMap.set(node.id, 0))
  graphData.edges.forEach(edge => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1)
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1)
  })

  const scoredNodes = [...graphData.nodes].sort((a, b) => {
    const scoreA = (degreeMap.get(a.id) || 0) + ((a.type || '').includes('人') ? 3 : 0)
    const scoreB = (degreeMap.get(b.id) || 0) + ((b.type || '').includes('人') ? 3 : 0)
    return scoreB - scoreA
  })

  const keptNodes = scoredNodes.slice(0, MAX_RENDER_NODES)
  const nodeIdSet = new Set(keptNodes.map(node => node.id))

  const keptEdges = graphData.edges
    .filter(edge => nodeIdSet.has(edge.source) && nodeIdSet.has(edge.target))
    .slice(0, MAX_RENDER_EDGES)

  const connectedNodeIds = new Set<string>()
  keptEdges.forEach(edge => {
    connectedNodeIds.add(edge.source)
    connectedNodeIds.add(edge.target)
  })

  const finalNodes = keptNodes.filter(node => connectedNodeIds.has(node.id)).slice(0, MAX_RENDER_NODES)

  renderNotice.value = `图谱较大，已优先展示 ${finalNodes.length} 个核心实体与 ${keptEdges.length} 条关系。`

  return {
    nodes: finalNodes,
    edges: keptEdges
  }
}

const getNodeDegree = (nodeId: string, direction: 'in' | 'out'): number => {
  return currentEdges.filter(edge => (direction === 'out' ? edge.source === nodeId : edge.target === nodeId))
    .length
}

const getNodeRelations = (nodeId: string): Array<{
  key: string
  direction: 'in' | 'out'
  source: string
  target: string
  label: string
}> => {
  const relations: Array<{
    key: string
    direction: 'in' | 'out'
    source: string
    target: string
    label: string
  }> = []

  for (const edge of currentEdges) {
    if (edge.source === nodeId) {
      relations.push({
        key: `out-${edge.source}-${edge.target}-${edge.label || ''}`,
        direction: 'out',
        source: edge.source,
        target: edge.target,
        label: edge.label || '关联'
      })
    } else if (edge.target === nodeId) {
      relations.push({
        key: `in-${edge.source}-${edge.target}-${edge.label || ''}`,
        direction: 'in',
        source: edge.source,
        target: edge.target,
        label: edge.label || '关联'
      })
    }
    if (relations.length >= 8) break
  }

  return relations
}

const toggleStats = async (): Promise<void> => {
  showStats.value = !showStats.value
  if (showStats.value && !graphStats.value) {
    await loadStats()
  }
}

const loadStats = async (): Promise<void> => {
  const kbId = resolveKbId()
  if (!kbId) return
  try {
    const res = await fetch(API_ENDPOINTS.KNOWLEDGE_GRAPH.GRAPH_STATS(kbId))
    if (!res.ok) return
    graphStats.value = (await res.json()) as GraphStats
  } catch {
    // Ignore stats loading failure.
  }
}

const fetchGraphData = async (): Promise<void> => {
  const kbId = resolveKbId()
  if (!kbId) {
    errorMessage.value = '未提供知识库 ID'
    return
  }

  isLoading.value = true
  loadingType.value = 'generate'
  errorMessage.value = ''

  try {
    const res = await fetch(API_ENDPOINTS.KNOWLEDGE_GRAPH.PROCESS_KNOWLEDGE_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder_path: kbId,
        deadline_sec: 120,
        max_chunks_per_file: 10,
        chunk_timeout_sec: 45,
        save_partial: true
      })
    })

    if (!res.ok) throw new Error(await getResponseMessage(res))

    const data = (await res.json()) as GeneratedGraphItem[] | GraphMessageResponse

    if (Array.isArray(data)) {
      const graphItems = data
        .map(item => item.graph_data)
        .filter((item): item is GraphData => Boolean(item))

      if (!graphItems.length) {
        errorMessage.value = '没有从知识库文档中提取到可视化图谱数据'
        clearGraph()
        return
      }

      updateGraph(mergeGraphData(graphItems))
      graphStats.value = null
      return
    }

    if (data?.message || data?.detail) {
      errorMessage.value = data.detail || data.message || '生成图谱失败'
      return
    }

    errorMessage.value = '返回数据格式不正确'
  } catch (error) {
    errorMessage.value = `生成图谱出错: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    isLoading.value = false
    loadingType.value = ''
  }
}

const fetchMergedGraph = async (): Promise<void> => {
  const kbId = resolveKbId()
  if (!kbId) {
    errorMessage.value = '未提供知识库 ID'
    return
  }

  isLoading.value = true
  loadingType.value = 'merged'
  errorMessage.value = ''
  isSearchMode.value = false

  try {
    const res = await fetch(API_ENDPOINTS.KNOWLEDGE_GRAPH.GET_MERGED_GRAPH(kbId))
    if (!res.ok) throw new Error(await getResponseMessage(res))
    const data = (await res.json()) as GraphMessageResponse

    if (data.message && !data.nodes?.length) {
      errorMessage.value = data.message
      clearGraph()
      return
    }

    updateGraph({
      nodes: data.nodes || [],
      edges: data.edges || []
    })
    graphStats.value = null
  } catch (error) {
    errorMessage.value = `加载全图出错: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    isLoading.value = false
    loadingType.value = ''
  }
}

const searchNodes = async (): Promise<void> => {
  const keyword = searchKeyword.value.trim()
  if (!keyword) return

  const kbId = resolveKbId()
  if (!kbId) {
    errorMessage.value = '未提供知识库 ID'
    return
  }

  isLoading.value = true
  loadingType.value = 'search'
  errorMessage.value = ''

  try {
    const res = await fetch(API_ENDPOINTS.KNOWLEDGE_GRAPH.SEARCH_NODES(kbId, keyword))
    if (!res.ok) throw new Error(await getResponseMessage(res))
    const data = (await res.json()) as GraphMessageResponse

    if (data.message) {
      errorMessage.value = data.message
      return
    }

    isSearchMode.value = true
    lastKeyword.value = keyword
    searchMatchCount.value = data.matched_count || 0

    updateGraph({
      nodes: data.nodes || [],
      edges: data.edges || []
    })
  } catch (error) {
    errorMessage.value = `搜索出错: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    isLoading.value = false
    loadingType.value = ''
  }
}

const clearSearch = (): void => {
  searchKeyword.value = ''
  isSearchMode.value = false
  lastKeyword.value = ''
  searchMatchCount.value = 0
  void fetchMergedGraph()
}

const clearGraph = (): void => {
  currentGraphData.value = null
  currentNodes = []
  currentEdges = []
  clearSelection()
  hasRenderedGraph.value = false
  renderNotice.value = ''
  destroyRenderer()
}

const clearSelection = (): void => {
  selectedNode.value = null
  applySelectionRef?.(null)
}

const updateGraph = (graphData: GraphData): void => {
  const normalized = normalizeGraphData(graphData)
  const trimmed = trimGraphForDisplay(normalized)

  currentNodes = trimmed.nodes
  currentEdges = trimmed.edges
  currentGraphData.value = trimmed
  selectedNode.value = null

  renderGraph(trimmed)
}

const destroyRenderer = (): void => {
  simulation?.stop()
  simulation = null
  zoomBehavior = null
  viewport = null
  applySelectionRef = null

  if (svg) {
    svg.remove()
    svg = null
  }
}

const asNodeId = (value: string | GraphNodeDatum): string => {
  return typeof value === 'string' ? value : value.id
}

const renderGraph = (graphData: GraphData): void => {
  const container = graphContainerRef.value
  if (!container) return

  destroyRenderer()
  hasRenderedGraph.value = false

  if (!graphData.nodes.length) {
    return
  }

  const width = Math.max(container.clientWidth, 720)
  const height = Math.max(container.clientHeight, 620)

  const degreeMap = new Map<string, number>()
  graphData.nodes.forEach(node => degreeMap.set(node.id, 0))
  graphData.edges.forEach(edge => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1)
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1)
  })

  const nodeData: GraphNodeDatum[] = graphData.nodes.map(node => {
    const degree = degreeMap.get(node.id) || 0
    const nodeType = node.type || '默认'
    return {
      id: node.id,
      label: node.label || node.name || node.id,
      type: nodeType,
      color: getNodeColor(nodeType),
      degree,
      size: Math.max(8, Math.min(24, 9 + degree * 1.2))
    }
  })

  const linkData: GraphLinkDatum[] = graphData.edges.map(edge => ({
    source: edge.source,
    target: edge.target,
    label: edge.label || '关联'
  }))

  const nodeById = new Map<string, GraphNodeDatum>(nodeData.map(node => [node.id, node]))
  const nodeFromLink = (value: string | GraphNodeDatum): GraphNodeDatum => {
    if (typeof value !== 'string') return value
    return (
      nodeById.get(value) || {
        id: value,
        label: value,
        type: '默认',
        color: NODE_COLORS.默认,
        degree: 0,
        size: 9
      }
    )
  }

  svg = d3
    .select(container)
    .append('svg')
    .attr('width', '100%')
    .attr('height', '100%')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('preserveAspectRatio', 'xMidYMid meet')
    .style('cursor', 'grab')

  viewport = svg.append('g').attr('class', 'viewport')
  const linkLayer = viewport.append('g').attr('class', 'links')
  const linkLabelLayer = viewport.append('g').attr('class', 'link-labels')
  const nodeLayer = viewport.append('g').attr('class', 'nodes')

  const linkSelection = linkLayer
    .selectAll<SVGLineElement, GraphLinkDatum>('line')
    .data(linkData)
    .join('line')
    .attr('stroke', '#9aa6b2')
    .attr('stroke-opacity', 0.52)
    .attr('stroke-width', 1.2)

  const linkLabelSelection = linkLabelLayer
    .selectAll<SVGTextElement, GraphLinkDatum>('text')
    .data(linkData.filter((item, index) => Boolean(item.label) && index < 260))
    .join('text')
    .text(item => item.label)
    .attr('font-size', 10)
    .attr('fill', '#64748b')
    .attr('text-anchor', 'middle')
    .style('pointer-events', 'none')
    .style('display', 'none')

  const nodeSelection = nodeLayer
    .selectAll<SVGGElement, GraphNodeDatum>('g')
    .data(nodeData, item => item.id)
    .join('g')
    .attr('class', 'kg-node')
    .style('cursor', 'pointer')

  nodeSelection
    .append('circle')
    .attr('r', item => item.size)
    .attr('fill', item => item.color)
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 1.2)

  nodeSelection
    .append('text')
    .text(item => item.label)
    .attr('x', item => item.size + 5)
    .attr('y', 4)
    .attr('font-size', 12)
    .attr('fill', '#111827')
    .attr('paint-order', 'stroke')
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 2)
    .attr('stroke-linejoin', 'round')
    .style('user-select', 'none')

  const applySelection = (nodeId: string | null): void => {
    nodeSelection.selectAll<SVGCircleElement, GraphNodeDatum>('circle')
      .attr('stroke', item => (nodeId && item.id === nodeId ? '#111827' : '#ffffff'))
      .attr('stroke-width', item => (nodeId && item.id === nodeId ? 2.4 : 1.2))
      .attr('r', item => (nodeId && item.id === nodeId ? item.size + 3 : item.size))

    linkSelection
      .attr('stroke-opacity', item => {
        if (!nodeId) return 0.52
        const sourceId = asNodeId(item.source)
        const targetId = asNodeId(item.target)
        return sourceId === nodeId || targetId === nodeId ? 0.85 : 0.12
      })
      .attr('stroke', item => {
        if (!nodeId) return '#9aa6b2'
        const sourceId = asNodeId(item.source)
        const targetId = asNodeId(item.target)
        return sourceId === nodeId || targetId === nodeId ? '#4f7ef8' : '#d1d5db'
      })

    linkLabelSelection.attr('fill-opacity', item => {
      if (!nodeId) return 0.88
      const sourceId = asNodeId(item.source)
      const targetId = asNodeId(item.target)
      return sourceId === nodeId || targetId === nodeId ? 1 : 0.15
    })
  }
  applySelectionRef = applySelection

  const dragBehavior = d3
    .drag<SVGGElement, GraphNodeDatum>()
    .on('start', (event, item) => {
      if (!event.active) {
        simulation?.alphaTarget(0.25).restart()
      }
      item.fx = item.x
      item.fy = item.y
    })
    .on('drag', (event, item) => {
      item.fx = event.x
      item.fy = event.y
    })
    .on('end', (event, item) => {
      if (!event.active) {
        simulation?.alphaTarget(0)
      }
      item.fx = null
      item.fy = null
    })

  nodeSelection.call(dragBehavior)

  nodeSelection.on('click', (event, item) => {
    event.stopPropagation()
    selectedNode.value = {
      id: item.id,
      label: item.label,
      type: item.type
    }
    applySelection(item.id)
  })

  svg.on('click', () => {
    clearSelection()
  })

  simulation = d3
    .forceSimulation(nodeData)
    .force(
      'link',
      d3.forceLink<GraphNodeDatum, GraphLinkDatum>(linkData).id(item => item.id).distance(108).strength(0.24)
    )
    .force('charge', d3.forceManyBody<GraphNodeDatum>().strength(item => -130 - Math.min(item.degree, 9) * 14))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide<GraphNodeDatum>().radius(item => item.size + 8).strength(0.95))
    .alpha(0.92)
    .alphaDecay(0.03)

  simulation.on('tick', () => {
    linkSelection
      .attr('x1', item => nodeFromLink(item.source).x ?? width / 2)
      .attr('y1', item => nodeFromLink(item.source).y ?? height / 2)
      .attr('x2', item => nodeFromLink(item.target).x ?? width / 2)
      .attr('y2', item => nodeFromLink(item.target).y ?? height / 2)

    nodeSelection.attr('transform', item => `translate(${item.x ?? width / 2}, ${item.y ?? height / 2})`)

    linkLabelSelection
      .attr('x', item => {
        const source = nodeFromLink(item.source)
        const target = nodeFromLink(item.target)
        return ((source.x ?? width / 2) + (target.x ?? width / 2)) / 2
      })
      .attr('y', item => {
        const source = nodeFromLink(item.source)
        const target = nodeFromLink(item.target)
        return ((source.y ?? height / 2) + (target.y ?? height / 2)) / 2
      })
  })

  zoomBehavior = d3
    .zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.35, 3.2])
    .on('start', () => {
      svg?.style('cursor', 'grabbing')
    })
    .on('end', () => {
      svg?.style('cursor', 'grab')
    })
    .on('zoom', event => {
      viewport?.attr('transform', event.transform.toString())
      const scale = event.transform.k
      nodeSelection.selectAll('text').style('display', scale > 0.72 ? 'block' : 'none')
      linkLabelSelection.style('display', scale > 1.18 ? 'block' : 'none')
    })

  svg.call(zoomBehavior)
  svg.on('dblclick.zoom', null)

  const fitGraph = (): void => {
    if (!svg || !zoomBehavior || !nodeData.length) return

    const xs = nodeData.map(item => item.x ?? width / 2)
    const ys = nodeData.map(item => item.y ?? height / 2)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)

    const graphWidth = Math.max(maxX - minX, 1)
    const graphHeight = Math.max(maxY - minY, 1)
    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2

    const scale = Math.min(width / (graphWidth + 220), height / (graphHeight + 220), 1.35)
    const tx = width / 2 - centerX * scale
    const ty = height / 2 - centerY * scale
    const transform = d3.zoomIdentity.translate(tx, ty).scale(scale)

    svg.transition().duration(280).call(zoomBehavior.transform, transform)
  }

  window.setTimeout(fitGraph, 320)
  hasRenderedGraph.value = true
}

const handleResize = (): void => {
  if (!currentGraphData.value) return
  renderGraph(currentGraphData.value)
}

watch(
  () => props.kbId,
  () => {
    clearGraph()
    graphStats.value = null
    showStats.value = false
    isSearchMode.value = false
    searchKeyword.value = ''
  }
)

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  destroyRenderer()
})
</script>

<style scoped>
.graph-container {
  position: relative;
  width: 100%;
}

.toolbar {
  position: relative;
}

.btn {
  border: none;
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 13px;
  line-height: 1.2;
  transition: all 0.2s ease;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn-primary {
  background: #3b82f6;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-success {
  background: #16a34a;
  color: #fff;
}

.btn-success:hover:not(:disabled) {
  background: #15803d;
}

.btn-search {
  background: #f3f4f6;
  color: #111827;
  border: 1px solid #d1d5db;
}

.btn-search:hover:not(:disabled) {
  background: #e5e7eb;
}

.btn-clear {
  background: #fff1f2;
  color: #be123c;
  border: 1px solid #fecdd3;
}

.btn-clear:hover {
  background: #ffe4e6;
}

.btn-stats {
  background: #f5f3ff;
  color: #6d28d9;
  border: 1px solid #ddd6fe;
}

.btn-stats:hover {
  background: #ede9fe;
}

.search-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.search-input {
  width: 160px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  outline: none;
}

.search-input:focus {
  border-color: #60a5fa;
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.2);
}

.stats-panel {
  position: absolute;
  top: 44px;
  right: 0;
  z-index: 20;
  width: 250px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.12);
  padding: 10px 12px;
}

.stats-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-weight: 600;
  color: #111827;
}

.stats-line {
  display: flex;
  justify-content: space-between;
  color: #475569;
  font-size: 12px;
  margin-bottom: 4px;
}

.stats-types {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e5e7eb;
}

.stats-types-title {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}

.stats-type-item {
  margin-bottom: 2px;
}

.close-btn {
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}

.close-btn:hover {
  color: #0f172a;
}

.error-box {
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
}

.notice-box {
  color: #1d4ed8;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
}

.search-hint {
  color: #2563eb;
  background: #eff6ff;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
}

.graph-stage {
  position: relative;
}

.graph-canvas {
  width: 100%;
  height: 640px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background:
    radial-gradient(circle at 12% 8%, rgba(79, 126, 248, 0.08), transparent 30%),
    radial-gradient(circle at 80% 85%, rgba(16, 185, 129, 0.06), transparent 35%),
    #fafafa;
  overflow: hidden;
}

.graph-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 14px;
  pointer-events: none;
}

.node-detail {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 15;
  width: 270px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.14);
  padding: 10px 12px;
  font-size: 12px;
  color: #334155;
  backdrop-filter: blur(4px);
}

.node-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.node-detail-line {
  margin-bottom: 5px;
  line-height: 1.5;
}

.type-tag {
  display: inline-block;
  color: #fff;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 11px;
  margin-left: 4px;
}

.relation-block {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
}

.relation-title {
  color: #64748b;
  margin-bottom: 6px;
}

.relation-item {
  margin-bottom: 4px;
}

.relation-label {
  color: #64748b;
  margin-left: 4px;
}

.slide-enter-active,
.slide-leave-active {
  transition:
    transform 0.2s ease,
    opacity 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(16px);
  opacity: 0;
}

@media (max-width: 1024px) {
  .graph-canvas {
    height: 560px;
  }

  .node-detail {
    width: min(270px, calc(100% - 20px));
  }
}
</style>
