import { Component, Input } from '@angular/core';

import { MessageMetrics } from './models';

const EMPTY_METRICS: MessageMetrics = {
  profile: 'optimized',
  model: '',
  temperature: null,
  max_tokens: null,
  context_window: null,
  thinking: false,
  request_started_at: null,
  total_latency_ms: null,
  ollama_total_duration_ms: null,
  load_duration_ms: null,
  input_tokens: null,
  output_tokens: null,
  total_tokens: null,
  prompt_eval_duration_ms: null,
  generation_duration_ms: null,
  prompt_tokens_per_second: null,
  generation_tokens_per_second: null,
  history_messages_count: null,
  history_chars: null,
  system_prompt_chars: null,
  user_prompt_chars: null,
  prompt_chars: null,
  success: false,
  error_type: null,
};

@Component({
  selector: 'app-message-metrics',
  standalone: true,
  template: `
    <div class="metric-summary">
      <span [class.profile-optimized]="metrics?.profile === 'optimized'">{{ profileLabel }}</span>
      <span aria-hidden="true">·</span>
      <span>{{ seconds(data.total_latency_ms) }} s</span>
      <span aria-hidden="true">·</span>
      <span>{{ value(data.input_tokens) }} → {{ value(data.output_tokens) }} tok</span>
      <span aria-hidden="true">·</span>
      <span>{{ speed(data.generation_tokens_per_second) }} tok/s</span>
    </div>

    <details class="metric-details">
      <summary>Метрики</summary>
      <dl>
        <div><dt>Профиль</dt><dd>{{ profileLabel }}</dd></div>
        <div><dt>Модель</dt><dd>{{ value(data.model) }}</dd></div>
        <div><dt>Temperature</dt><dd>{{ value(data.temperature) }}</dd></div>
        <div><dt>Max output</dt><dd>{{ value(data.max_tokens) }}</dd></div>
        <div><dt>Context</dt><dd>{{ value(data.context_window) }}</dd></div>
        <div><dt>Thinking</dt><dd>{{ booleanValue(metrics?.thinking, 'On', 'Off') }}</dd></div>
        <div><dt>Старт запроса</dt><dd>{{ dateTime(data.request_started_at) }}</dd></div>
        <div><dt>Общая задержка</dt><dd>{{ milliseconds(data.total_latency_ms) }}</dd></div>
        <div><dt>Ollama total</dt><dd>{{ milliseconds(data.ollama_total_duration_ms) }}</dd></div>
        <div><dt>Загрузка модели</dt><dd>{{ milliseconds(data.load_duration_ms) }}</dd></div>
        <div><dt>Prompt eval</dt><dd>{{ milliseconds(data.prompt_eval_duration_ms) }}</dd></div>
        <div><dt>Генерация</dt><dd>{{ milliseconds(data.generation_duration_ms) }}</dd></div>
        <div><dt>Input tokens</dt><dd>{{ value(data.input_tokens) }}</dd></div>
        <div><dt>Output tokens</dt><dd>{{ value(data.output_tokens) }}</dd></div>
        <div><dt>Total tokens</dt><dd>{{ value(data.total_tokens) }}</dd></div>
        <div><dt>Prompt speed</dt><dd>{{ speedWithUnit(data.prompt_tokens_per_second) }}</dd></div>
        <div><dt>Generation speed</dt><dd>{{ speedWithUnit(data.generation_tokens_per_second) }}</dd></div>
        <div><dt>Сообщений в истории</dt><dd>{{ value(data.history_messages_count) }}</dd></div>
        <div><dt>Символов истории</dt><dd>{{ value(data.history_chars) }}</dd></div>
        <div><dt>Символов system prompt</dt><dd>{{ value(data.system_prompt_chars) }}</dd></div>
        <div><dt>Символов user prompt</dt><dd>{{ value(data.user_prompt_chars) }}</dd></div>
        <div><dt>Символов prompt всего</dt><dd>{{ value(data.prompt_chars) }}</dd></div>
        <div><dt>Успех</dt><dd>{{ booleanValue(metrics?.success, 'Да', 'Нет') }}</dd></div>
        <div><dt>Тип ошибки</dt><dd>{{ value(data.error_type) }}</dd></div>
      </dl>
    </details>
  `,
  styles: `
    :host { display: block; min-width: 0; margin-top: 11px; font-family: 'JetBrains Mono', monospace; }
    .metric-summary { display: flex; flex-wrap: wrap; gap: 4px 7px; color: #718099; font-size: 9px; line-height: 1.5; }
    .metric-summary > span:first-child { color: #315ee7; font-weight: 700; }
    .metric-summary > .profile-optimized { color: #c36a18; }
    .metric-details { margin-top: 5px; color: #64738b; font-size: 9px; }
    summary { width: fit-content; color: #536681; cursor: pointer; font-family: 'Manrope Variable', sans-serif; font-weight: 700; }
    summary:hover { color: #315ee7; }
    dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; max-width: 650px; margin: 8px 0 0; border-top: 1px solid #dce3ed; border-left: 1px solid #dce3ed; }
    dl div { display: grid; grid-template-columns: minmax(115px, 1fr) minmax(60px, auto); gap: 10px; padding: 6px 8px; border-right: 1px solid #dce3ed; border-bottom: 1px solid #dce3ed; background: rgba(255, 255, 255, 0.55); }
    dt { min-width: 0; overflow-wrap: anywhere; }
    dd { min-width: 0; margin: 0; color: #263b5b; text-align: right; overflow-wrap: anywhere; }
    :host-context(.comparison-response) dl { grid-template-columns: minmax(0, 1fr); }
    :host-context(.comparison-response) dl div { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    @media (max-width: 620px) { dl { grid-template-columns: 1fr; } }
  `,
})
export class MessageMetricsComponent {
  @Input({ required: true }) metrics: MessageMetrics | null = null;

  get data(): MessageMetrics {
    return this.metrics ?? EMPTY_METRICS;
  }

  get profileLabel(): string {
    if (!this.metrics) {
      return '—';
    }
    return this.metrics.profile === 'baseline' ? 'Baseline' : 'Optimized';
  }

  value(value: string | number | null | undefined): string | number {
    return value === '' || value == null ? '—' : value;
  }

  seconds(value: number | null): string {
    return value == null ? '—' : (value / 1000).toFixed(1);
  }

  milliseconds(value: number | null): string {
    return value == null ? '—' : `${this.number(value)} ms`;
  }

  speed(value: number | null): string {
    return value == null ? '—' : this.number(value);
  }

  speedWithUnit(value: number | null): string {
    return value == null ? '—' : `${this.number(value)} tok/s`;
  }

  booleanValue(value: boolean | undefined, trueLabel: string, falseLabel: string): string {
    return value == null ? '—' : value ? trueLabel : falseLabel;
  }

  dateTime(value: string | null): string {
    if (!value) {
      return '—';
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU');
  }

  private number(value: number): string {
    return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
  }
}
