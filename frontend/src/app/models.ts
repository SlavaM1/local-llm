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
}

export interface MessageExchange {
  user_message: Message;
  assistant_message: Message;
  chat: Chat;
}

export interface Health {
  status: string;
  ollama: 'available' | 'unavailable';
  model: string;
}
