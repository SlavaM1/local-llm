import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Chat, Health, Message, MessageExchange, Provider } from './models';

@Injectable({ providedIn: 'root' })
export class ChatApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api';

  getHealth(): Observable<Health> {
    return this.http.get<Health>(`${this.baseUrl}/health`);
  }

  getChats(): Observable<Chat[]> {
    return this.http.get<Chat[]>(`${this.baseUrl}/chats`);
  }

  createChat(): Observable<Chat> {
    return this.http.post<Chat>(`${this.baseUrl}/chats`, {});
  }

  deleteChat(chatId: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/chats/${chatId}`);
  }

  getMessages(chatId: number): Observable<Message[]> {
    return this.http.get<Message[]>(`${this.baseUrl}/chats/${chatId}/messages`);
  }

  sendMessage(
    chatId: number,
    content: string,
    provider: Provider,
    ragEnabled: boolean,
  ): Observable<MessageExchange> {
    return this.http.post<MessageExchange>(`${this.baseUrl}/chats/${chatId}/messages`, {
      content,
      provider,
      rag_enabled: ragEnabled,
    });
  }
}
