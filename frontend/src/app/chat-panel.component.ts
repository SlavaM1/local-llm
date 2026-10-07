import { Component, ElementRef, EventEmitter, Input, OnChanges, Output, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { MarkdownPipe } from './markdown.pipe';
import { Chat, Message, Provider, SendMessageRequest } from './models';

@Component({
  selector: 'app-chat-panel',
  standalone: true,
  imports: [FormsModule, MarkdownPipe],
  template: `
    <main class="chat-panel">
      <header class="chat-header">
        <button class="menu-button" type="button" aria-label="Открыть меню" (click)="menu.emit()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <div class="header-copy">
          <h1>{{ activeChat?.title || 'Локальный интеллект' }}</h1>
          <p>{{ activeChat ? 'Контекст этого диалога сохранён' : 'Локальный или облачный режим на каждый запрос' }}</p>
        </div>
        <div class="local-badge"><span></span> {{ provider === 'ollama' ? 'local' : 'cloud' }}</div>
      </header>

      <section #messageList class="messages" aria-live="polite">
        @if (!activeChat) {
          <div class="welcome">
            <div class="welcome-orbit" aria-hidden="true"><span></span></div>
            <h2>Режим выбираете вы.</h2>
            <p>
              Qwen3 работает на вашем компьютере, DeepSeek использует облако, а история хранится
              локально. Создайте чат, чтобы начать.
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
            @for (message of messages; track message.id) {
              <article class="message" [class.message--user]="message.role === 'user'">
                <div class="message-node" aria-hidden="true">
                  {{ message.role === 'assistant' ? 'Q' : 'В' }}
                </div>
                <div class="message-body">
                  <div class="message-author">
                    {{ message.role === 'assistant' ? assistantAuthor(message) : 'Вы' }}
                  </div>
                  @if (message.role === 'assistant') {
                    <div class="markdown" [innerHTML]="message.content | markdown"></div>
                    @if (message.status === 'insufficient_context') {
                      <div class="answer-status">Недостаточно контекста в базе знаний</div>
                    }
                    <div class="answer-summary">
                      <span>{{ message.model || 'qwen3:8b' }}</span>
                      <span>RAG {{ message.rag_enabled ? 'ON' : 'OFF' }}</span>
                      @if (metric(message, 'total_latency_ms') !== null) {
                        <span>{{ formatMetric(metric(message, 'total_latency_ms')) }} ms</span>
                      }
                      @if (metric(message, 'input_tokens') !== null || metric(message, 'output_tokens') !== null) {
                        <span>{{ formatMetric(metric(message, 'input_tokens')) }}→{{ formatMetric(metric(message, 'output_tokens')) }} tok</span>
                      }
                      @if (metric(message, 'generation_tokens_per_second') !== null) {
                        <span>{{ formatMetric(metric(message, 'generation_tokens_per_second')) }} tok/s</span>
                      }
                    </div>
                    @if (message.metrics) {
                      <details class="message-details">
                        <summary>Метрики</summary>
                        <dl class="metric-grid">
                          @for (row of metricRows(message.metrics); track row.key) {
                            <dt>{{ row.label }}</dt><dd>{{ row.value }}</dd>
                          }
                        </dl>
                      </details>
                    }
                    @if (message.sources?.length) {
                      <details class="message-details">
                        <summary>Источники · {{ message.sources.length }}</summary>
                        <div class="evidence-list">
                          @for (source of message.sources; track $index) {
                            <div class="evidence-item">
                              <strong>{{ value(source.source || source.file) }}</strong>
                              <span>{{ value(source.section) }}</span>
                              <code>{{ value(source.chunk_id) }}</code>
                              <small>similarity {{ value(source.similarity_score ?? source.score) }} · rank {{ value(source.final_rank) }}</small>
                            </div>
                          }
                        </div>
                      </details>
                    }
                    @if (message.quotes?.length) {
                      <details class="message-details">
                        <summary>Цитаты · {{ message.quotes.length }}</summary>
                        <div class="evidence-list">
                          @for (quote of message.quotes; track $index) {
                            <blockquote>{{ value(quote.quote) }}</blockquote>
                          }
                        </div>
                      </details>
                    }
                  } @else {
                    <div class="user-content">{{ message.content }}</div>
                  }
                </div>
              </article>
            }

            @if (loading) {
              <article class="message thinking">
                <div class="message-node" aria-hidden="true">Q</div>
                <div class="message-body">
                  <div class="message-author">{{ provider === 'deepseek' ? 'DeepSeek Flash' : 'Qwen3 8B' }}</div>
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
        @if (errorMessage) {
          <div class="error-message" role="alert">{{ errorMessage }}</div>
        }
        <div class="turn-controls" aria-label="Настройки следующего сообщения">
          <label>
            <span>Модель</span>
            <select [ngModel]="provider" [disabled]="busy" (ngModelChange)="providerChange.emit($event)">
              <option value="ollama">Qwen3 8B Local</option>
              <option value="deepseek">DeepSeek Flash Cloud</option>
            </select>
          </label>
          <button
            class="rag-toggle"
            type="button"
            [disabled]="busy"
            [class.rag-toggle--active]="ragEnabled"
            [attr.aria-pressed]="ragEnabled"
            (click)="ragEnabledChange.emit(!ragEnabled)"
          >RAG {{ ragEnabled ? 'ON' : 'OFF' }}</button>
        </div>
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
        <p class="composer-hint">Enter — отправить <span>Shift + Enter — новая строка</span></p>
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
  @Input() provider: Provider = 'ollama';
  @Input() ragEnabled = false;

  @Output() readonly send = new EventEmitter<SendMessageRequest>();
  @Output() readonly providerChange = new EventEmitter<Provider>();
  @Output() readonly ragEnabledChange = new EventEmitter<boolean>();
  @Output() readonly newChat = new EventEmitter<void>();
  @Output() readonly menu = new EventEmitter<void>();

  @ViewChild('messageList') private messageList?: ElementRef<HTMLElement>;

  draft = '';

  get canSend(): boolean {
    return Boolean(this.activeChat && this.draft.trim() && !this.busy && !this.loadingHistory);
  }

  ngOnChanges(): void {
    window.requestAnimationFrame(() => this.scrollToBottom());
  }

  handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submit();
    }
  }

  submit(): void {
    const content = this.draft.trim();
    if (!content || !this.canSend) {
      return;
    }
    this.draft = '';
    this.send.emit({ content, provider: this.provider, rag_enabled: this.ragEnabled });
  }

  assistantAuthor(message: Message): string {
    if (message.model) {
      return `${message.provider === 'deepseek' ? 'DeepSeek' : 'Ollama'} · ${message.model}`;
    }
    return message.provider === 'deepseek' ? 'DeepSeek Flash' : 'Qwen3 8B';
  }

  metric(message: Message, name: string): unknown | null {
    const value = message.metrics?.[name];
    return value === undefined ? null : value;
  }

  formatMetric(value: unknown): string {
    if (value === null || value === undefined) {
      return '—';
    }
    if (typeof value === 'number') {
      return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.00$/, '');
    }
    if (typeof value === 'boolean') {
      return value ? 'yes' : 'no';
    }
    return String(value);
  }

  value(value: unknown): string {
    return this.formatMetric(value);
  }

  metricRows(metrics: Record<string, unknown>): Array<{ key: string; label: string; value: string }> {
    const rows: Array<{ key: string; label: string; value: string }> = [];
    const visit = (value: unknown, path: string): void => {
      if (Array.isArray(value)) {
        if (value.length === 0) {
          rows.push({ key: path, label: path, value: '—' });
        } else {
          value.forEach((item, index) => visit(item, `${path}[${index + 1}]`));
        }
      } else if (value !== null && typeof value === 'object') {
        const entries = Object.entries(value as Record<string, unknown>);
        if (entries.length === 0) {
          rows.push({ key: path, label: path, value: '—' });
        } else {
          entries.forEach(([key, item]) => visit(item, path ? `${path}.${key}` : key));
        }
      } else {
        rows.push({ key: path, label: path.replaceAll('_', ' '), value: this.formatMetric(value) });
      }
    };
    Object.entries(metrics).forEach(([key, value]) => visit(value, key));
    return rows;
  }

  resizeTextarea(event: Event): void {
    const textarea = event.target as HTMLTextAreaElement;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }

  private scrollToBottom(): void {
    const element = this.messageList?.nativeElement;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }
}
