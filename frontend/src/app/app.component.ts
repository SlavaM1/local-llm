import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectorRef, Component, OnInit, inject } from '@angular/core';
import { finalize } from 'rxjs';

import { ChatApiService } from './chat-api.service';
import { ChatPanelComponent } from './chat-panel.component';
import { Chat, Message, Provider, SendMessageRequest } from './models';
import { SidebarComponent } from './sidebar.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [SidebarComponent, ChatPanelComponent],
  template: `
    <div class="app-shell">
      <app-sidebar
        [chats]="chats"
        [selectedId]="activeChat?.id ?? null"
        [ollamaAvailable]="ollamaAvailable"
        [ragAvailable]="ragAvailable"
        [creating]="creatingChat"
        [open]="sidebarOpen"
        (create)="createChat()"
        (select)="selectChat($event)"
        (delete)="deleteChat($event)"
        (close)="sidebarOpen = false"
      />
      @if (sidebarOpen) {
        <button class="mobile-backdrop" aria-label="Закрыть меню" (click)="sidebarOpen = false"></button>
      }
      <app-chat-panel
        [activeChat]="activeChat"
        [messages]="messages"
        [loading]="isSending(activeChat?.id)"
        [busy]="isSending(activeChat?.id)"
        [loadingHistory]="loadingMessages"
        [errorMessage]="errorMessage"
        [provider]="provider"
        [ragEnabled]="ragEnabled"
        (providerChange)="provider = $event"
        (ragEnabledChange)="ragEnabled = $event"
        (send)="sendMessage($event)"
        (newChat)="createChat()"
        (menu)="sidebarOpen = true"
      />
    </div>
  `,
  styles: `
    :host { display: block; height: 100%; }
    .app-shell { display: flex; height: 100%; overflow: hidden; }
    .mobile-backdrop { display: none; }
    @media (max-width: 760px) {
      .mobile-backdrop {
        position: fixed;
        z-index: 15;
        inset: 0;
        display: block;
        border: 0;
        background: rgba(16, 29, 52, 0.48);
        backdrop-filter: blur(2px);
      }
    }
  `,
})
export class AppComponent implements OnInit {
  private readonly api = inject(ChatApiService);
  private readonly changeDetector = inject(ChangeDetectorRef);

  chats: Chat[] = [];
  activeChat: Chat | null = null;
  messages: Message[] = [];
  ollamaAvailable = false;
  ragAvailable = false;
  provider: Provider = 'ollama';
  ragEnabled = false;
  creatingChat = false;
  loadingMessages = false;
  sidebarOpen = false;
  errorMessage = '';
  private messageRequestId = 0;
  private chatListRevision = 0;
  private readonly sendingChatIds = new Set<number>();

  ngOnInit(): void {
    this.api.getHealth().subscribe({
      next: (health) => {
        this.ollamaAvailable = health.ollama === 'available';
        this.ragAvailable = health.rag === 'available';
      },
      error: () => {
        this.ollamaAvailable = false;
        this.ragAvailable = false;
      },
    });
    this.loadChats();
  }

  createChat(): void {
    if (this.creatingChat) {
      return;
    }
    this.creatingChat = true;
    this.errorMessage = '';
    this.api
      .createChat()
      .pipe(
        finalize(() => {
          this.creatingChat = false;
          this.changeDetector.markForCheck();
        }),
      )
      .subscribe({
        next: (chat) => {
          this.chatListRevision++;
          this.chats = [chat, ...this.chats];
          this.messageRequestId++;
          this.activeChat = chat;
          this.messages = [];
          this.loadingMessages = false;
          this.sidebarOpen = false;
          this.changeDetector.markForCheck();
        },
        error: (error: HttpErrorResponse) => (this.errorMessage = this.readError(error)),
      });
  }

  selectChat(chat: Chat): void {
    const requestId = ++this.messageRequestId;
    this.activeChat = chat;
    this.messages = [];
    this.loadingMessages = true;
    this.errorMessage = '';
    this.sidebarOpen = false;
    this.api
      .getMessages(chat.id)
      .pipe(
        finalize(() => {
          if (requestId === this.messageRequestId) {
            this.loadingMessages = false;
            this.changeDetector.markForCheck();
          }
        }),
      )
      .subscribe({
        next: (messages) => {
          if (requestId === this.messageRequestId && this.activeChat?.id === chat.id) {
            this.messages = messages;
          }
        },
        error: (error: HttpErrorResponse) => {
          if (requestId === this.messageRequestId) {
            this.errorMessage = this.readError(error);
          }
        },
      });
  }

  deleteChat(chat: Chat): void {
    this.errorMessage = '';
    this.api.deleteChat(chat.id).subscribe({
      next: () => {
        this.chatListRevision++;
        this.chats = this.chats.filter((item) => item.id !== chat.id);
        if (this.activeChat?.id === chat.id) {
          this.messageRequestId++;
          this.activeChat = null;
          this.messages = [];
          this.loadingMessages = false;
        }
      },
      error: (error: HttpErrorResponse) => (this.errorMessage = this.readError(error)),
    });
  }

  sendMessage(request: SendMessageRequest): void {
    const chat = this.activeChat;
    if (!chat || this.sendingChatIds.has(chat.id)) {
      return;
    }

    const temporaryId = -Date.now();
    this.messages = [
      ...this.messages,
      {
        id: temporaryId,
        chat_id: chat.id,
        role: 'user',
        content: request.content,
        created_at: new Date().toISOString(),
      },
    ];
    this.sendingChatIds.add(chat.id);
    this.errorMessage = '';

    this.api
      .sendMessage(chat.id, request.content, request.provider, request.rag_enabled)
      .pipe(
        finalize(() => {
          this.sendingChatIds.delete(chat.id);
          this.changeDetector.markForCheck();
        }),
      )
      .subscribe({
        next: (exchange) => {
          this.chatListRevision++;
          this.chats = [exchange.chat, ...this.chats.filter((item) => item.id !== chat.id)];
          if (this.activeChat?.id === chat.id) {
            this.messages = [
              ...this.messages.filter(
                (message) =>
                  message.id !== temporaryId &&
                  message.id !== exchange.user_message.id &&
                  message.id !== exchange.assistant_message.id,
              ),
              exchange.user_message,
              exchange.assistant_message,
            ].sort((left, right) => left.id - right.id);
            this.activeChat = exchange.chat;
          }
          if (request.provider === 'ollama' && !request.rag_enabled) {
            this.ollamaAvailable = true;
          } else {
            this.ragAvailable = true;
          }
        },
        error: (error: HttpErrorResponse) => {
          if ((error.status === 0 || error.status === 503) && request.provider === 'ollama' && !request.rag_enabled) {
            this.ollamaAvailable = false;
          }
          if ((error.status === 0 || error.status === 503 || error.status === 504) && (request.rag_enabled || request.provider === 'deepseek')) {
            this.ragAvailable = false;
          }
          if (this.activeChat?.id === chat.id) {
            this.errorMessage = this.readError(error);
            this.reloadMessages(chat.id);
          }
        },
      });
  }

  isSending(chatId: number | null | undefined): boolean {
    return chatId != null && this.sendingChatIds.has(chatId);
  }

  private loadChats(): void {
    const revision = this.chatListRevision;
    this.api.getChats().subscribe({
      next: (chats) => {
        if (revision !== this.chatListRevision) {
          return;
        }
        this.chats = chats;
        if (chats.length > 0) {
          this.selectChat(chats[0]);
        }
      },
      error: (error: HttpErrorResponse) => (this.errorMessage = this.readError(error)),
    });
  }

  private reloadMessages(chatId: number): void {
    this.api.getMessages(chatId).subscribe({
      next: (messages) => {
        if (this.activeChat?.id === chatId) {
          this.messages = messages;
        }
      },
    });
  }

  private readError(error: HttpErrorResponse): string {
    const detail = error.error?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return 'Не удалось выполнить запрос. Проверьте, что локальные сервисы запущены.';
  }
}
