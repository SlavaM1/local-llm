import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map, timeout } from 'rxjs';

import {
  Chat,
  CompareExchange,
  CompareRequest,
  AuthUser,
  Health,
  Message,
  MessageExchange,
  ModelProfilesResponse,
  SendMessageRequest,
  ServiceSettings,
} from './models';

@Injectable({ providedIn: 'root' })
export class ChatApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api';

  getHealth(): Observable<Health> {
    return this.http.get<Health>(`${this.baseUrl}/health`);
  }

  login(username: string, password: string): Observable<AuthUser> {
    return this.http.post<AuthUser>(`${this.baseUrl}/auth/login`, { username, password });
  }

  getMe(): Observable<AuthUser> {
    return this.http.get<AuthUser>(`${this.baseUrl}/auth/me`);
  }

  logout(): Observable<void> {
    return this.http.post<void>(`${this.baseUrl}/auth/logout`, {});
  }

  getServiceSettings(): Observable<ServiceSettings> {
    return this.http.get<ServiceSettings>(`${this.baseUrl}/settings`);
  }

  updateServiceSettings(settings: ServiceSettings): Observable<ServiceSettings> {
    return this.http.put<ServiceSettings>(`${this.baseUrl}/settings`, settings);
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

  getModelProfiles(): Observable<ModelProfilesResponse> {
    return this.http
      .get<Partial<ModelProfilesResponse>>(`${this.baseUrl}/model-profiles`)
      .pipe(
        timeout({ first: 15_000 }),
        map((response) => ({
          profiles: Array.isArray(response.profiles) ? response.profiles : [],
          allowed: response.allowed ?? {},
        })),
      );
  }

  sendMessage(chatId: number, request: SendMessageRequest): Observable<MessageExchange> {
    return this.http
      .post<MessageExchange>(`${this.baseUrl}/chats/${chatId}/messages`, request)
      .pipe(timeout({ first: 610_000 }));
  }

  compareMessages(chatId: number, request: CompareRequest): Observable<CompareExchange> {
    return this.http
      .post<CompareExchange>(`${this.baseUrl}/chats/${chatId}/compare`, request)
      .pipe(timeout({ first: 1_215_000 }));
  }
}
