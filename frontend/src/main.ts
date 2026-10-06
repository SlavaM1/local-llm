import localeRu from '@angular/common/locales/ru';
import { registerLocaleData } from '@angular/common';
import { provideHttpClient } from '@angular/common/http';
import { LOCALE_ID } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';

import { AppComponent } from './app/app.component';

registerLocaleData(localeRu);

bootstrapApplication(AppComponent, {
  providers: [provideHttpClient(), { provide: LOCALE_ID, useValue: 'ru-RU' }],
}).catch((error: unknown) => console.error(error));
