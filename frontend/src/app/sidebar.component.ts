import { DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';

import { Chat } from './models';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [DatePipe],
  template: `
    <aside class="sidebar" [class.sidebar--open]="open">
      <div class="brand-row">
        <div class="brand-mark" aria-hidden="true"><span></span></div>
        <div>
          <div class="brand">Local LLM</div>
          <div class="brand-note">Приватный AI-чат</div>
        </div>
        <button class="close-button" type="button" aria-label="Закрыть меню" (click)="close.emit()">
          ×
        </button>
      </div>

      <div class="account-row">
        <span>{{ username }}</span>
        <button type="button" (click)="settings.emit()">Настройки</button>
        <button type="button" (click)="logout.emit()">Выйти</button>
      </div>

      <div class="model-status" [class.model-status--offline]="!ollamaAvailable">
        <span class="status-dot"></span>
        <span>
          <strong>Qwen3 8B</strong>
          <small>{{ ollamaAvailable ? 'работает локально' : 'Ollama недоступна' }}</small>
        </span>
      </div>

      <button class="new-chat" type="button" (click)="create.emit()" [disabled]="creating">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
        {{ creating ? 'Создаём...' : 'Новый чат' }}
      </button>

      <div class="history-heading">
        <span>История</span>
        <span>{{ chats.length }}</span>
      </div>

      <nav class="chat-list" aria-label="История диалогов">
        @for (chat of chats; track chat.id) {
          <div class="chat-row" [class.chat-row--active]="chat.id === selectedId">
            <button class="chat-select" type="button" (click)="select.emit(chat)">
              <span class="chat-title">{{ chat.title }}</span>
              <span class="chat-date">{{ chat.updated_at | date: 'd MMM, HH:mm' }}</span>
            </button>
            <button
              class="delete-button"
              type="button"
              aria-label="Удалить диалог"
              title="Удалить диалог"
              (click)="confirmDelete(chat)"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
              </svg>
            </button>
          </div>
        } @empty {
          <p class="empty-history">Здесь появятся ваши диалоги.</p>
        }
      </nav>

      <p class="privacy-note">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 3 5 6v5c0 4.8 2.8 8.1 7 10 4.2-1.9 7-5.2 7-10V6l-7-3Z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
        Данные остаются на этом устройстве
      </p>
    </aside>
  `,
  styleUrl: './sidebar.component.css',
})
export class SidebarComponent {
  @Input({ required: true }) chats: Chat[] = [];
  @Input() selectedId: number | null = null;
  @Input() ollamaAvailable = false;
  @Input() creating = false;
  @Input() open = false;
  @Input() username = '';

  @Output() readonly create = new EventEmitter<void>();
  @Output() readonly select = new EventEmitter<Chat>();
  @Output() readonly delete = new EventEmitter<Chat>();
  @Output() readonly close = new EventEmitter<void>();
  @Output() readonly settings = new EventEmitter<void>();
  @Output() readonly logout = new EventEmitter<void>();

  confirmDelete(chat: Chat): void {
    if (window.confirm('Удалить этот диалог?')) {
      this.delete.emit(chat);
    }
  }
}
