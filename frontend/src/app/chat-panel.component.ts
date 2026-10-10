import { Component, ElementRef, EventEmitter, Input, OnChanges, Output, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { MarkdownPipe } from './markdown.pipe';
import { MessageMetricsComponent } from './message-metrics.component';
import {
  DEFAULT_OPTIMIZED_SETTINGS,
  Chat,
  Message,
  ModelProfile,
  ModelSettings,
  ProfileName,
} from './models';

interface ThreadItem {
  key: string;
  comparison: boolean;
  message: Message | null;
  userMessage: Message | null;
  assistantMessages: Message[];
}

@Component({
  selector: 'app-chat-panel',
  standalone: true,
  imports: [FormsModule, MarkdownPipe, MessageMetricsComponent],
  template: `
    <main class="chat-panel">
      <header class="chat-header">
        <button class="menu-button" type="button" aria-label="Открыть меню" (click)="menu.emit()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <div class="header-copy">
          <h1>{{ activeChat?.title || 'Локальный интеллект' }}</h1>
          <p>{{ activeChat ? 'Контекст этого диалога сохранён' : 'Без облака. Без передачи данных.' }}</p>
        </div>
        <div class="local-badge"><span></span> local</div>
      </header>

      <section #messageList class="messages" aria-live="polite">
        @if (!activeChat) {
          <div class="welcome">
            <div class="welcome-orbit" aria-hidden="true"><span></span></div>
            <h2>Разговор остаётся здесь.</h2>
            <p>
              Qwen3 работает на вашем компьютере, а история хранится локально. Создайте чат,
              чтобы начать.
            </p>
            <button type="button" (click)="newChat.emit()">Создать первый диалог</button>
          </div>
        } @else if (messages.length === 0 && !loading && !loadingHistory) {
          <div class="welcome welcome--compact">
            <div class="prompt-mark" aria-hidden="true">?</div>
            <h2>О чём поговорим?</h2>
            <p>Модель запомнит предыдущие сообщения внутри этого диалога.</p>
          </div>
        } @else {
          <div class="thread">
            @for (item of threadItems; track item.key) {
              @if (item.comparison) {
                @if (item.userMessage; as userMessage) {
                  <article class="message message--user">
                    <div class="message-node" aria-hidden="true">В</div>
                    <div class="message-body">
                      <div class="message-author">Вы</div>
                      <div class="user-content">{{ userMessage.content }}</div>
                    </div>
                  </article>
                }
                @if (item.assistantMessages.length > 0) {
                  <section class="comparison-block" aria-label="Сравнение ответов Baseline и Optimized">
                    <div class="comparison-heading">
                      <span>Сравнение профилей</span>
                      <span class="comparison-id">{{ compactComparisonId(item.key) }}</span>
                    </div>
                    <div class="comparison-grid">
                      @for (message of item.assistantMessages; track message.id) {
                        <article
                          class="comparison-response"
                          [class.comparison-response--optimized]="message.metrics?.profile === 'optimized'"
                        >
                          <div class="comparison-profile">
                            <span></span>{{ messageProfileLabel(message) }}
                          </div>
                          <div class="markdown" [innerHTML]="message.content | markdown"></div>
                          <app-message-metrics [metrics]="message.metrics" />
                        </article>
                      }
                    </div>
                  </section>
                }
              } @else if (item.message; as message) {
                <article class="message" [class.message--user]="message.role === 'user'">
                  <div class="message-node" aria-hidden="true">
                    {{ message.role === 'assistant' ? 'Q' : 'В' }}
                  </div>
                  <div class="message-body">
                    <div class="message-author">
                      {{ message.role === 'assistant' ? 'Qwen3' : 'Вы' }}
                    </div>
                    @if (message.role === 'assistant') {
                      <div class="markdown" [innerHTML]="message.content | markdown"></div>
                      <app-message-metrics [metrics]="message.metrics" />
                    } @else {
                      <div class="user-content">{{ message.content }}</div>
                    }
                  </div>
                </article>
              }
            }

            @if (loading) {
              <article class="message thinking">
                <div class="message-node" aria-hidden="true">Q</div>
                <div class="message-body">
                  <div class="message-author">Qwen3</div>
                  <div class="thinking-row">
                    <span></span><span></span><span></span>
                    <em>Модель думает...</em>
                  </div>
                </div>
              </article>
            }
          </div>
        }
      </section>

      <footer class="composer-area">
        <div class="profile-toolbar">
          <div class="profile-segments" role="group" aria-label="Профиль модели">
            <button
              type="button"
              [class.active]="selectedProfile === 'baseline'"
              [attr.aria-pressed]="selectedProfile === 'baseline'"
              (click)="selectProfile('baseline')"
            >
              Baseline
            </button>
            <button
              type="button"
              [class.active]="selectedProfile === 'optimized'"
              [class.custom]="isOptimizedCustom"
              [attr.aria-pressed]="selectedProfile === 'optimized'"
              (click)="selectProfile('optimized')"
            >
              Optimized{{ isOptimizedCustom ? ' (custom)' : '' }}
            </button>
          </div>

          <details class="model-settings">
            <summary>Настройки модели</summary>
            @if (selectedProfile === 'baseline') {
              <div class="settings-grid settings-grid--readonly">
                <div><span>Model</span><strong>{{ baselineProfile?.model || 'qwen3:8b' }}</strong></div>
                <div><span>Temperature</span><strong>—</strong></div>
                <div><span>Max output</span><strong>—</strong></div>
                <div><span>Context</span><strong>—</strong></div>
                <div><span>Thinking</span><strong>Off</strong></div>
              </div>
            } @else {
              <div class="settings-grid">
                <div class="setting-readonly">
                  <span>Model</span><strong>{{ optimizedProfile?.model || 'qwen3:8b' }}</strong>
                </div>
                <label class="temperature-control">
                  <span>Temperature <output>{{ optimizedSettings.temperature.toFixed(1) }}</output></span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    [ngModel]="optimizedSettings.temperature"
                    (ngModelChange)="setTemperature($event)"
                  />
                </label>
                <label>
                  <span>Max output</span>
                  <select
                    [ngModel]="optimizedSettings.max_tokens"
                    (ngModelChange)="setMaxTokens($event)"
                  >
                    <option [ngValue]="256">256</option>
                    <option [ngValue]="512">512</option>
                    <option [ngValue]="1024">1024</option>
                  </select>
                </label>
                <label>
                  <span>Context</span>
                  <select
                    [ngModel]="optimizedSettings.context_window"
                    (ngModelChange)="setContextWindow($event)"
                  >
                    <option [ngValue]="2048">2048</option>
                    <option [ngValue]="4096">4096</option>
                  </select>
                </label>
                <label>
                  <span>Thinking</span>
                  <select [ngModel]="optimizedSettings.thinking" (ngModelChange)="setThinking($event)">
                    <option [ngValue]="false">Off</option>
                    <option [ngValue]="true">On</option>
                  </select>
                </label>
              </div>
            }
          </details>
        </div>

        @if (errorMessage) {
          <div class="error-message" role="alert">{{ errorMessage }}</div>
        }
        <div class="composer" [class.composer--disabled]="!activeChat">
          <textarea
            [(ngModel)]="draft"
            [disabled]="!activeChat || busy || loadingHistory"
            rows="1"
            maxlength="20000"
            placeholder="Напишите сообщение..."
            aria-label="Сообщение"
            (keydown)="handleKeydown($event)"
            (input)="resizeTextarea($event)"
          ></textarea>
          <button
            type="button"
            aria-label="Отправить сообщение"
            title="Отправить"
            [disabled]="!canSend"
            (click)="submit()"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 14-7-4 14-3-6-7-1Z" />
              <path d="m12 13 7-8" />
            </svg>
          </button>
        </div>
        <div class="composer-actions">
          <button type="button" class="compare-button" [disabled]="!canSend" (click)="submitComparison()">
            Сравнить Baseline / Optimized
          </button>
          <p class="composer-hint">Enter — отправить <span>Shift + Enter — новая строка</span></p>
        </div>
      </footer>
    </main>
  `,
  styleUrl: './chat-panel.component.css',
})
export class ChatPanelComponent implements OnChanges {
  @Input() activeChat: Chat | null = null;
  @Input({ required: true }) messages: Message[] = [];
  @Input() loading = false;
  @Input() busy = false;
  @Input() loadingHistory = false;
  @Input() errorMessage = '';
  @Input() selectedProfile: ProfileName = 'optimized';
  @Input({ required: true }) optimizedSettings: ModelSettings = { ...DEFAULT_OPTIMIZED_SETTINGS };
  @Input({ required: true }) modelProfiles: ModelProfile[] = [];

  @Output() readonly send = new EventEmitter<string>();
  @Output() readonly compare = new EventEmitter<string>();
  @Output() readonly profileChange = new EventEmitter<ProfileName>();
  @Output() readonly settingsChange = new EventEmitter<ModelSettings>();
  @Output() readonly newChat = new EventEmitter<void>();
  @Output() readonly menu = new EventEmitter<void>();

  @ViewChild('messageList') private messageList?: ElementRef<HTMLElement>;

  draft = '';
  threadItems: ThreadItem[] = [];

  get canSend(): boolean {
    return Boolean(this.activeChat && this.draft.trim() && !this.busy && !this.loadingHistory);
  }

  get isOptimizedCustom(): boolean {
    return (
      this.optimizedSettings.temperature !== DEFAULT_OPTIMIZED_SETTINGS.temperature ||
      this.optimizedSettings.max_tokens !== DEFAULT_OPTIMIZED_SETTINGS.max_tokens ||
      this.optimizedSettings.context_window !== DEFAULT_OPTIMIZED_SETTINGS.context_window ||
      this.optimizedSettings.thinking !== DEFAULT_OPTIMIZED_SETTINGS.thinking
    );
  }

  get baselineProfile(): ModelProfile | undefined {
    return this.modelProfiles.find((profile) => profile.id === 'baseline');
  }

  get optimizedProfile(): ModelProfile | undefined {
    return this.modelProfiles.find((profile) => profile.id === 'optimized');
  }

  ngOnChanges(): void {
    this.threadItems = this.groupMessages(this.messages);
    window.requestAnimationFrame(() => this.scrollToBottom());
  }

  handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submit();
    }
  }

  submit(): void {
    const content = this.takeDraft();
    if (content) {
      this.send.emit(content);
    }
  }

  submitComparison(): void {
    const content = this.takeDraft();
    if (content) {
      this.compare.emit(content);
    }
  }

  selectProfile(profile: ProfileName): void {
    this.profileChange.emit(profile);
  }

  setTemperature(value: number | string): void {
    const temperature = Math.min(1, Math.max(0, Number(value)));
    this.updateSettings({ temperature: Math.round(temperature * 10) / 10 });
  }

  setMaxTokens(value: ModelSettings['max_tokens']): void {
    this.updateSettings({ max_tokens: value });
  }

  setContextWindow(value: ModelSettings['context_window']): void {
    this.updateSettings({ context_window: value });
  }

  setThinking(value: boolean): void {
    this.updateSettings({ thinking: value });
  }

  resizeTextarea(event: Event): void {
    const textarea = event.target as HTMLTextAreaElement;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }

  messageProfileLabel(message: Message): string {
    if (!message.metrics) {
      return '—';
    }
    return message.metrics.profile === 'baseline' ? 'Baseline' : 'Optimized';
  }

  compactComparisonId(key: string): string {
    const id = key.replace('comparison-', '');
    return id.length > 12 ? `#${id.slice(0, 8)}` : `#${id}`;
  }

  private takeDraft(): string | null {
    const content = this.draft.trim();
    if (!content || !this.canSend) {
      return null;
    }
    this.draft = '';
    return content;
  }

  private updateSettings(update: Partial<ModelSettings>): void {
    this.settingsChange.emit({ ...this.optimizedSettings, ...update });
  }

  private groupMessages(messages: Message[]): ThreadItem[] {
    const items: ThreadItem[] = [];
    const comparisons = new Map<string, ThreadItem>();

    for (const message of messages) {
      if (!message.comparison_id) {
        items.push({
          key: `message-${message.id}`,
          comparison: false,
          message,
          userMessage: null,
          assistantMessages: [],
        });
        continue;
      }

      let item = comparisons.get(message.comparison_id);
      if (!item) {
        item = {
          key: `comparison-${message.comparison_id}`,
          comparison: true,
          message: null,
          userMessage: null,
          assistantMessages: [],
        };
        comparisons.set(message.comparison_id, item);
        items.push(item);
      }

      if (message.role === 'user') {
        item.userMessage ??= message;
      } else {
        item.assistantMessages.push(message);
      }
    }

    for (const item of comparisons.values()) {
      item.assistantMessages.sort(
        (left, right) => this.profileOrder(left) - this.profileOrder(right) || left.id - right.id,
      );
    }
    return items;
  }

  private profileOrder(message: Message): number {
    return message.metrics?.profile === 'baseline' ? 0 : 1;
  }

  private scrollToBottom(): void {
    const element = this.messageList?.nativeElement;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }
}
