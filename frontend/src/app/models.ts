export interface Chat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  chat_id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  request_id?: string | null;
  provider?: Provider | null;
  model?: string | null;
  rag_enabled?: boolean | null;
  status?: string | null;
  metrics?: Record<string, unknown> | null;
  sources?: Source[];
  quotes?: Quote[];
}

export type Provider = 'ollama' | 'deepseek';

export interface Source {
  source?: unknown;
  file?: unknown;
  section?: unknown;
  chunk_id?: unknown;
  similarity_score?: unknown;
  score?: unknown;
  final_rank?: unknown;
}

export interface Quote {
  quote?: unknown;
  source_number?: unknown;
  source?: unknown;
  file?: unknown;
  section?: unknown;
  chunk_id?: unknown;
}

export interface SendMessageRequest {
  content: string;
  provider: Provider;
  rag_enabled: boolean;
}

export interface MessageExchange {
  user_message: Message;
  assistant_message: Message;
  chat: Chat;
}

export interface Health {
  status: string;
  backend: 'ok';
  ollama: 'available' | 'unavailable';
  rag: 'available' | 'unavailable';
  deepseek_configured: boolean;
  model: string;
}
