import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectorRef, Component, OnInit, inject } from '@angular/core';
import { TimeoutError, finalize } from 'rxjs';

import { ChatApiService } from './chat-api.service';
import { ChatPanelComponent } from './chat-panel.component';
import {
  DEFAULT_OPTIMIZED_SETTINGS,
  Chat,
  Message,
  ModelProfile,
  ModelSettings,
  ProfileName,
} from './models';
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
        [selectedProfile]="selectedProfile"
        [optimizedSettings]="optimizedSettings"
        [modelProfiles]="modelProfiles"
        (send)="sendMessage($event)"
        (compare)="compareMessages($event)"
        (profileChange)="selectedProfile = $event"
        (settingsChange)="optimizedSettings = $event"
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
  creatingChat = false;
  loadingMessages = false;
  sidebarOpen = false;
  errorMessage = '';
  selectedProfile: ProfileName = 'optimized';
  optimizedSettings: ModelSettings = { ...DEFAULT_OPTIMIZED_SETTINGS };
  modelProfiles: ModelProfile[] = [
    {
      id: 'baseline',
      label: 'Baseline',
      model: 'qwen3:8b',
      system_prompt: '',
      temperature: null,
      max_tokens: null,
      context_window: null,
      top_p: null,
      repeat_penalty: null,
      thinking: false,
      customizable: false,
    },
    {
      id: 'optimized',
      label: 'Optimized',
      model: 'qwen3:8b',
      system_prompt: '',
      temperature: DEFAULT_OPTIMIZED_SETTINGS.temperature,
      max_tokens: DEFAULT_OPTIMIZED_SETTINGS.max_tokens,
      context_window: DEFAULT_OPTIMIZED_SETTINGS.context_window,
      top_p: null,
      repeat_penalty: null,
      thinking: DEFAULT_OPTIMIZED_SETTINGS.thinking,
      customizable: true,
    },
  ];
  private messageRequestId = 0;
  private chatListRevision = 0;
  private readonly sendingChatIds = new Set<number>();

  ngOnInit(): void {
    this.api.getHealth().subscribe({
      next: (health) => (this.ollamaAvailable = health.ollama === 'available'),
      error: () => (this.ollamaAvailable = false),
    });
    this.api.getModelProfiles().subscribe({
      next: ({ profiles }) => {
        if (profiles.length > 0) {
          this.modelProfiles = this.modelProfiles.map(
            (fallback) => profiles.find((profile) => profile.id === fallback.id) ?? fallback,
          );
        }
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

  sendMessage(content: string): void {
    const chat = this.activeChat;
    if (!chat || this.sendingChatIds.has(chat.id)) {
      return;
    }

    const temporaryId = -Date.now();
    this.messages = [
      ...this.messages,
      this.temporaryUserMessage(temporaryId, chat.id, content, null),
    ];
    this.sendingChatIds.add(chat.id);
    this.errorMessage = '';

    const profile = this.selectedProfile;
    const settings = { ...this.optimizedSettings };

    this.api
      .sendMessage(chat.id, {
        content,
        profile,
        ...(profile === 'optimized' ? { settings } : {}),
      })
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
          this.ollamaAvailable = true;
        },
        error: (error: unknown) => {
          if (this.isModelUnavailable(error)) {
            this.ollamaAvailable = false;
          }
          if (this.activeChat?.id === chat.id) {
            this.errorMessage = this.readError(error);
            this.reloadMessages(chat.id);
          }
        },
      });
  }

  compareMessages(content: string): void {
    const chat = this.activeChat;
    if (!chat || this.sendingChatIds.has(chat.id)) {
      return;
    }

    const temporaryId = -Date.now();
    const pendingComparisonId = `pending-${chat.id}-${Math.abs(temporaryId)}`;
    this.messages = [
      ...this.messages,
      this.temporaryUserMessage(temporaryId, chat.id, content, pendingComparisonId),
    ];
    this.sendingChatIds.add(chat.id);
    this.errorMessage = '';
    const optimizedSettings = { ...this.optimizedSettings };

    this.api
      .compareMessages(chat.id, { content, optimized_settings: optimizedSettings })
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
            const returnedMessages = [
              exchange.user_message,
              exchange.baseline_message,
              exchange.optimized_message,
            ];
            const returnedIds = new Set(returnedMessages.map((message) => message.id));
            this.messages = [
              ...this.messages.filter(
                (message) => message.id !== temporaryId && !returnedIds.has(message.id),
              ),
              ...returnedMessages,
            ].sort((left, right) => left.id - right.id);
            this.activeChat = exchange.chat;
          }
          this.ollamaAvailable = true;
        },
        error: (error: unknown) => {
          if (this.isModelUnavailable(error)) {
            this.ollamaAvailable = false;
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

  private temporaryUserMessage(
    id: number,
    chatId: number,
    content: string,
    comparisonId: string | null,
  ): Message {
    return {
      id,
      chat_id: chatId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      comparison_id: comparisonId,
      metrics: null,
    };
  }

  private isModelUnavailable(error: unknown): boolean {
    return error instanceof HttpErrorResponse && (error.status === 0 || error.status === 503);
  }

  private readError(error: unknown): string {
    if (error instanceof TimeoutError) {
      return 'Модель не ответила вовремя. Попробуйте ещё раз или уменьшите контекст.';
    }
    if (error instanceof HttpErrorResponse) {
      const detail = error.error?.detail;
      if (typeof detail === 'string') {
        return detail;
      }
      if (error.status === 0) {
        return 'Нет связи с локальным API. Проверьте, что сервис запущен.';
      }
      if (error.status === 200) {
        return 'Сервер вернул ответ в неожиданном формате.';
      }
    }
    return 'Не удалось выполнить запрос. Проверьте, что локальные сервисы запущены.';
  }
}
