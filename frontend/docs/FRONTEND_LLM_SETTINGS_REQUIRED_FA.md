# چیزهایی که حتماً باید در فرانت اضافه شوند

فرانت فعلی React + TypeScript + Vite است و API پایه آن باید این مقدار باشد:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_MOCK_FALLBACK=false
```

برای جلوگیری از مشکل Cookie، فرانت را هم با همان hostname اجرا کنید:

```powershell
npm run dev -- --host 127.0.0.1
```

آدرس فرانت:

```text
http://127.0.0.1:5173
```

## 1. تمام درخواست‌ها باید Cookie را ارسال کنند

در `fetch`:

```ts
credentials: 'include'
```

خود API Key در Cookie نیست. Cookie فقط Session ID را نگه می‌دارد و `HttpOnly` است؛ بنابراین JavaScript فرانت به آن دسترسی ندارد.

## 2. صفحه Settings باید این کنترل‌ها را داشته باشد

- Provider: `Gemini`، `OpenAI` و برای حالت توسعه `Mock`
- API Key با `type="password"`
- دکمه نمایش/پنهان‌کردن مقدار تایپ‌شده
- دکمه «دریافت مدل‌ها»
- Dropdown انتخاب مدل
- دکمه «آزمایش اتصال»
- Checkbox «روی این دستگاه به خاطر سپرده شود»
- دکمه «ذخیره تنظیمات»
- دکمه «حذف کلید»
- Status Chip برای `configured / not configured / test passed / error`

متن ثابت پیشنهادی در صفحه:

> کلید API داخل LocalStorage یا Cookie ذخیره نمی‌شود. در حالت موقت فقط در حافظه Backend محلی نگه‌داری می‌شود. با فعال‌کردن «به خاطر سپردن»، کلید در Windows Credential Manager ذخیره می‌شود. کلید کامل پس از ذخیره دوباره نمایش داده نمی‌شود.

همچنین این هشدار کوتاه نمایش داده شود:

> اشتراک ChatGPT یا Gemini App به‌تنهایی اعتبار API محسوب نمی‌شود و هزینه API ممکن است جداگانه محاسبه شود.

## 3. ترتیب UX صفحه Settings

1. هنگام بازشدن صفحه: `GET /api/settings/llm`
2. کاربر Provider را انتخاب می‌کند.
3. کاربر API Key را وارد می‌کند.
4. با «دریافت مدل‌ها»: `POST /api/settings/llm/models`
5. مدل از Dropdown انتخاب می‌شود.
6. با «آزمایش اتصال»: `POST /api/settings/llm/test`
7. فقط بعد از Test موفق، دکمه Save فعال شود.
8. با Save: `PUT /api/settings/llm`
9. پس از Save، فیلد API Key فوراً خالی شود.
10. در صفحه پرسش‌وپاسخ Provider و Model فعال از `GET /api/config/client` نمایش داده شود.

## 4. قرارداد Endpointهای تنظیمات

### وضعیت فعلی

```http
GET /api/settings/llm
```

نمونه پاسخ:

```json
{
  "active_provider": "gemini",
  "providers": [
    {
      "provider": "gemini",
      "configured": true,
      "selected": true,
      "model": "model-id",
      "key_preview": "AIza••••••••abcd",
      "remembered_on_device": true
    }
  ],
  "session_storage": "http_only_cookie_plus_backend_memory",
  "persistent_storage": "windows_credential_manager_when_enabled",
  "key_is_returned_to_frontend": false
}
```

### دریافت مدل‌ها

```http
POST /api/settings/llm/models
Content-Type: application/json
```

```json
{
  "provider": "gemini",
  "api_key": "کلید تایپ‌شده یا null برای استفاده از کلید ذخیره‌شده"
}
```

### آزمایش اتصال

```http
POST /api/settings/llm/test
```

```json
{
  "provider": "gemini",
  "model": "model-id",
  "api_key": "کلید تایپ‌شده یا null"
}
```

### ذخیره

```http
PUT /api/settings/llm
```

```json
{
  "provider": "gemini",
  "model": "model-id",
  "api_key": "کلید یا null برای نگه‌داشتن کلید قبلی",
  "remember_on_device": true
}
```

### حذف کلید یک Provider

```http
DELETE /api/settings/llm?provider=gemini
```

### حذف همه کلیدها

```http
DELETE /api/settings/llm
```

## 5. تغییر کوچک در صفحه Question

برای سؤال عادی لازم نیست Provider یا Model در هر درخواست ارسال شود. Backend از تنظیمات Session استفاده می‌کند:

```json
{
  "question": "شرایط مهمانی دانشجو چیست؟",
  "top_k": 5,
  "category": null
}
```

ارسال `provider` و `model` همچنان برای Override اختیاری پشتیبانی می‌شود.

## 6. مواردی که نباید در فرانت انجام شوند

- ذخیره API Key در `localStorage`
- ذخیره API Key در `sessionStorage`
- گذاشتن API Key در `VITE_*`
- نمایش کلید کامل پس از ذخیره
- نوشتن Key در Console یا Error Log
- فرستادن درخواست بدون `credentials: 'include'`
- اجرای Backend روی `0.0.0.0` برای این پروژه شخصی
