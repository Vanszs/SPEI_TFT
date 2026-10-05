import { ref, onMounted, onUnmounted, type Ref } from 'vue';

export interface WeatherData {
  temp_c: number;
  humidity_pct: number;
  precip_mm: number;
  et0_mm: number;
}

export interface InferenceState {
  model_status: string;
  latest_spei_p50: number;
  drought_risk: string;
}

export interface StreamPayload {
  type: string;
  city_id: string;
  timestamp: string;
  step: number;
  weather: WeatherData;
  inference_state: InferenceState;
}

export interface UseDroughtStreamOptions {
  cityId?: string;
  mode?: 'sse' | 'websocket';
  sseUrl?: string;
  wsUrl?: string;
  enabled?: boolean;
}

export interface UseDroughtStreamReturn {
  data: Ref<StreamPayload | null>;
  isConnected: Ref<boolean>;
  error: Ref<string | null>;
  sendWsMessage: (msg: unknown) => void;
}

export function useDroughtStream({
  cityId = 'surabaya',
  mode = 'sse',
  sseUrl = '/api/v1/stream/weather',
  wsUrl = '/ws/monitoring',
  enabled = true,
}: UseDroughtStreamOptions = {}): UseDroughtStreamReturn {
  const data = ref<StreamPayload | null>(null);
  const isConnected = ref<boolean>(false);
  const error = ref<string | null>(null);

  let eventSource: EventSource | null = null;
  let ws: WebSocket | null = null;

  const closeConnections = () => {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    isConnected.value = false;
  };

  const connect = () => {
    if (!enabled) return;

    error.value = null;

    if (mode === 'sse') {
      const url = `${sseUrl}?city_id=${encodeURIComponent(cityId)}`;
      const es = new EventSource(url);
      eventSource = es;

      es.onopen = () => {
        isConnected.value = true;
      };

      es.addEventListener('weather_update', (event) => {
        try {
          const parsed = JSON.parse(event.data) as StreamPayload;
          data.value = parsed;
        } catch (e) {
          console.error('Failed to parse SSE payload', e);
        }
      });

      es.onerror = () => {
        isConnected.value = false;
        error.value = 'SSE connection error';
        es.close();
      };
    } else if (mode === 'websocket') {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const fullWsUrl = wsUrl.startsWith('ws') ? wsUrl : `${protocol}//${window.location.host}${wsUrl}`;
      const socket = new WebSocket(fullWsUrl);
      ws = socket;

      socket.onopen = () => {
        isConnected.value = true;
        socket.send(JSON.stringify({ action: 'subscribe', city_id: cityId }));
      };

      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.weather) {
            data.value = parsed as StreamPayload;
          }
        } catch (e) {
          console.error('Failed to parse WS payload', e);
        }
      };

      socket.onerror = () => {
        isConnected.value = false;
        error.value = 'WebSocket error';
      };

      socket.onclose = () => {
        isConnected.value = false;
      };
    }
  };

  onMounted(() => {
    connect();
  });

  onUnmounted(() => {
    closeConnections();
  });

  const sendWsMessage = (msg: unknown) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
  };

  return { data, isConnected, error, sendWsMessage };
}
