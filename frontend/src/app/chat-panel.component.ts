import { Component, ElementRef, EventEmitter, Input, OnChanges, Output, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { MarkdownPipe } from './markdown.pipe';
import { Chat, Message } from './models';

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
            @for (message of messages; track message.id) {
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

  @Output() readonly send = new EventEmitter<string>();
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
    this.send.emit(content);
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
