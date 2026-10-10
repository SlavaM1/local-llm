import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectorRef, Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
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
  AuthUser,
  ServiceSettings,
} from './models';
import { SidebarComponent } from './sidebar.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [FormsModule, SidebarComponent, ChatPanelComponent],
  template: `
    @if (!user) {
      <section class="auth-shell">
        <form class="auth-card" (ngSubmit)="login()">
          <div class="auth-mark">LL</div>
          <h1>Local LLM</h1>
          <p>Для работы авторизируйтесь</p>
          @if (authError) { <div class="auth-error" role="alert">{{ authError }}</div> }
          <label>Логин<input name="username" [(ngModel)]="loginUsername" autocomplete="username" [disabled]="loginLoading" /></label>
          <label>Пароль<input name="password" [(ngModel)]="loginPassword" type="password" autocomplete="current-password" [disabled]="loginLoading" /></label>
          <button type="submit" [disabled]="loginLoading || !loginUsername || !loginPassword">{{ loginLoading ? 'Входим...' : 'Войти' }}</button>
        </form>
      </section>
    } @else {
    <div class="app-shell">
      <app-sidebar
        [chats]="chats"
        [selectedId]="activeChat?.id ?? null"
        [ollamaAvailable]="ollamaAvailable"
        [creating]="creatingChat"
        [open]="sidebarOpen"
        [username]="user.username"
        (create)="createChat()"
        (select)="selectChat($event)"
        (delete)="deleteChat($event)"
        (close)="sidebarOpen = false"
        (settings)="openSettings()"
        (logout)="logout()"
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
    @if (settingsOpen) {
      <div class="settings-backdrop" (click)="settingsOpen = false">
        <form class="settings-dialog" (click)="$event.stopPropagation()" (ngSubmit)="saveServiceSettings()">
          <button class="settings-close" type="button" aria-label="Закрыть" (click)="settingsOpen = false">×</button>
          <p class="settings-eyebrow">Приватный сервис</p>
          <h2>Настройки сервиса</h2>
          <label>Rate limit<input name="rateLimit" type="number" min="1" max="1000" step="1" [(ngModel)]="serviceSettings.requests_per_minute" /> <small>запросов / минуту</small></label>
          <label>Max context<input name="maxContext" type="number" min="1024" max="8192" step="1" [(ngModel)]="serviceSettings.max_context_tokens" /> <small>tokens</small></label>
          <p class="settings-hint">Рекомендуемый context для RTX 3070 8 GB: 4096</p>
          @if (settingsError) { <p class="auth-error">{{ settingsError }}</p> }
          <button type="submit" [disabled]="settingsSaving">{{ settingsSaving ? 'Сохраняем...' : 'Сохранить' }}</button>
        </form>
      </div>
    }
    }
  `,
  styles: `
    :host { display: block; height: 100%; }
    .app-shell { display: flex; height: 100%; overflow: hidden; }
    .mobile-backdrop { display: none; }
    .auth-shell { display: grid; min-height: 100%; place-items: center; padding: 24px; background: radial-gradient(circle at 10% 10%, #dbe7ff, transparent 34%), #f3f6fa; }
    .auth-card { width: min(100%, 380px); padding: 34px; border: 1px solid #dce3ed; border-radius: 18px; background: #fff; box-shadow: 0 22px 56px rgba(25, 49, 90, .13); }
    .auth-mark { display: grid; width: 42px; height: 42px; place-items: center; color: #fff; border-radius: 12px; background: #315ee7; font: 700 12px 'JetBrains Mono', monospace; }
    .auth-card h1 { margin: 18px 0 5px; font-size: 26px; } .auth-card p { margin: 0 0 22px; color: #64738c; font-size: 14px; }
    .auth-card label, .settings-dialog label { display: grid; gap: 6px; margin-top: 15px; color: #465a78; font-size: 12px; font-weight: 700; }
    .auth-card input, .settings-dialog input { width: 100%; padding: 11px 12px; color: #172641; border: 1px solid #cbd7e8; border-radius: 9px; background: #fff; font: inherit; }
    .auth-card button, .settings-dialog > button:last-child { width: 100%; margin-top: 22px; padding: 12px; color: #fff; border: 0; border-radius: 9px; background: #315ee7; font: 700 13px inherit; cursor: pointer; }
    button:disabled { cursor: wait; opacity: .65; } .auth-error { margin: 14px 0 0 !important; color: #a63833 !important; }
    .settings-backdrop { position: fixed; z-index: 40; inset: 0; display: grid; place-items: center; padding: 20px; background: rgba(14, 31, 58, .48); }
    .settings-dialog { position: relative; width: min(100%, 430px); padding: 28px; border-radius: 16px; background: #fff; box-shadow: 0 22px 56px rgba(0, 0, 0, .25); }
    .settings-dialog h2 { margin: 3px 0 6px; font-size: 21px; } .settings-eyebrow { margin: 0; color: #315ee7; font: 700 10px 'JetBrains Mono', monospace; text-transform: uppercase; }
    .settings-dialog small { color: #718099; font-weight: 500; } .settings-hint { margin: 18px 0 0; color: #64738c; font-size: 12px; }
    .settings-close { position: absolute; top: 12px; right: 14px; padding: 3px 8px; color: #64738c; border: 0; background: none; font-size: 24px; cursor: pointer; }
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

  user: AuthUser | null = null;
  loginUsername = 'admin';
  loginPassword = '';
  loginLoading = false;
  authError = '';
  settingsOpen = false;
  settingsSaving = false;
  settingsError = '';
  serviceSettings: ServiceSettings = { requests_per_minute: 20, max_context_tokens: 4096 };

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
    this.api.getMe().subscribe({
      next: (user) => this.completeAuthentication(user),
      error: () => undefined,
    });
  }

  login(): void {
    if (this.loginLoading || !this.loginUsername || !this.loginPassword) {
      return;
    }
    this.loginLoading = true;
    this.authError = '';
    this.api.login(this.loginUsername, this.loginPassword).pipe(
      finalize(() => {
        this.loginLoading = false;
        this.changeDetector.markForCheck();
      }),
    ).subscribe({
      next: (user) => {
        this.loginPassword = '';
        this.completeAuthentication(user);
      },
      error: (error: unknown) => {
        this.authError = error instanceof HttpErrorResponse && error.status === 429
          ? 'Слишком много попыток. Попробуйте позже.'
          : 'Неверный логин или пароль';
      },
    });
  }

  logout(): void {
    this.api.logout().subscribe({ complete: () => this.endSession('') , error: () => this.endSession('') });
  }

  openSettings(): void {
    this.settingsError = '';
    this.settingsOpen = true;
  }

  saveServiceSettings(): void {
    const requestsPerMinute = Number(this.serviceSettings.requests_per_minute);
    const maxContextTokens = Number(this.serviceSettings.max_context_tokens);
    if (!Number.isInteger(requestsPerMinute) || requestsPerMinute < 1 || requestsPerMinute > 1000 ||
        !Number.isInteger(maxContextTokens) || maxContextTokens < 1024 || maxContextTokens > 8192) {
      this.settingsError = 'Введите целые значения: 1–1000 запросов и 1024–8192 tokens.';
      return;
    }
    this.settingsSaving = true;
    this.settingsError = '';
    this.api.updateServiceSettings({ requests_per_minute: requestsPerMinute, max_context_tokens: maxContextTokens }).pipe(
      finalize(() => {
        this.settingsSaving = false;
        this.changeDetector.markForCheck();
      }),
    ).subscribe({
      next: (settings) => {
        this.serviceSettings = settings;
        this.settingsOpen = false;
      },
      error: (error: unknown) => this.settingsError = this.readError(error),
    });
  }

  private completeAuthentication(user: AuthUser): void {
    this.user = user;
    this.api.getHealth().subscribe({
      next: (health) => (this.ollamaAvailable = health.status === 'ok'),
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
    this.api.getServiceSettings().subscribe({
      next: (settings) => (this.serviceSettings = settings),
      error: (error: unknown) => (this.errorMessage = this.readError(error)),
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
      error: (error: unknown) => this.readError(error),
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
      if (error.status === 401) {
        this.endSession('Сессия истекла. Авторизуйтесь снова.');
        return 'Сессия истекла. Авторизуйтесь снова.';
      }
      if (error.status === 429) {
        const retryAfter = error.headers.get('Retry-After');
        return `Превышен лимит запросов. Попробуйте через ${retryAfter ?? 'несколько'} сек.`;
      }
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

  private endSession(message: string): void {
    this.messageRequestId++;
    this.sendingChatIds.clear();
    this.user = null;
    this.chats = [];
    this.activeChat = null;
    this.messages = [];
    this.loadingMessages = false;
    this.creatingChat = false;
    this.sidebarOpen = false;
    this.settingsOpen = false;
    this.errorMessage = '';
    this.authError = message;
    this.changeDetector.markForCheck();
  }
}
