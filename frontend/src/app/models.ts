export interface Chat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export type ProfileName = 'baseline' | 'optimized';

export interface ModelSettings {
  temperature: number;
  max_tokens: 256 | 512 | 1024;
  context_window: 2048 | 4096;
  thinking: boolean;
}

export const DEFAULT_OPTIMIZED_SETTINGS: Readonly<ModelSettings> = {
  temperature: 0.2,
  max_tokens: 512,
  context_window: 4096,
  thinking: false,
};

export interface ModelProfile {
  id: ProfileName;
  label: string;
  model: string;
  system_prompt: string;
  temperature: number | null;
  max_tokens: number | null;
  context_window: number | null;
  top_p: number | null;
  repeat_penalty: number | null;
  thinking: boolean;
  customizable: boolean;
}

export interface ModelProfileOptions {
  temperatures?: number[];
  max_tokens?: number[];
  context_windows?: number[];
  thinking?: boolean[];
}

export interface ModelProfilesResponse {
  profiles: ModelProfile[];
  allowed: ModelProfileOptions;
}

export interface MessageMetrics {
  profile: ProfileName;
  model: string;
  temperature: number | null;
  max_tokens: number | null;
  context_window: number | null;
  thinking: boolean;
  request_started_at: string | null;
  total_latency_ms: number | null;
  ollama_total_duration_ms: number | null;
  load_duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  prompt_eval_duration_ms: number | null;
  generation_duration_ms: number | null;
  prompt_tokens_per_second: number | null;
  generation_tokens_per_second: number | null;
  history_messages_count: number | null;
  history_chars: number | null;
  system_prompt_chars: number | null;
  user_prompt_chars: number | null;
  prompt_chars: number | null;
  success: boolean;
  error_type: string | null;
}

export interface Message {
  id: number;
  chat_id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  comparison_id: string | null;
  metrics: MessageMetrics | null;
}

export interface MessageExchange {
  user_message: Message;
  assistant_message: Message;
  chat: Chat;
}

export interface CompareExchange {
  user_message: Message;
  baseline_message: Message;
  optimized_message: Message;
  chat: Chat;
}

export interface SendMessageRequest {
  content: string;
  profile: ProfileName;
  settings?: ModelSettings;
}

export interface CompareRequest {
  content: string;
  optimized_settings?: ModelSettings;
}

export interface Health {
  status: string;
}

export interface AuthUser {
  username: string;
}

export interface ServiceSettings {
  requests_per_minute: number;
  max_context_tokens: number;
}
