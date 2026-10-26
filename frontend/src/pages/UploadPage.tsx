import { CheckCircle2, FileUp, Loader2, UploadCloud } from 'lucide-react';
import { ChangeEvent, DragEvent, useState } from 'react';
import { uploadDocument } from '../api/client';

interface UploadItem {
  id: string;
  file: File;
  status: 'waiting' | 'uploading' | 'done' | 'error';
  message?: string;
}

export default function UploadPage() {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);

  function addFiles(files: FileList | File[]) {
    const pdfs = Array.from(files).filter((file) => file.type === 'application/pdf');
    setItems((current) => [
      ...current,
      ...pdfs.map((file) => ({
        id: crypto.randomUUID(),
        file,
        status: 'waiting' as const,
      })),
    ]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = '';
  }

  async function uploadAll() {
    for (const item of items.filter((entry) => entry.status === 'waiting')) {
      setItems((current) =>
        current.map((entry) =>
          entry.id === item.id ? { ...entry, status: 'uploading' } : entry,
        ),
      );

      try {
        const result = await uploadDocument(item.file);
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id
              ? { ...entry, status: 'done', message: result.message }
              : entry,
          ),
        );
      } catch (caught) {
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id
              ? {
                  ...entry,
                  status: 'error',
                  message: caught instanceof Error ? caught.message : 'خطا',
                }
              : entry,
          ),
        );
      }
    }
  }

  return (
    <div className="page secondary-page">
      <header className="section-header">
        <div>
          <span className="eyebrow">افزودن داده جدید</span>
          <h1>آپلود سند</h1>
          <p>فایل‌های PDF را برای ورود به خط لوله پردازش انتخاب کنید.</p>
        </div>
      </header>

      <div
        className={`upload-dropzone ${dragging ? 'is-dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <UploadCloud size={47} />
        <h2>فایل‌های PDF را اینجا رها کنید</h2>
        <p>یا با دکمه زیر فایل‌ها را انتخاب کنید.</p>
        <label className="primary-button">
          <FileUp size={19} />
          انتخاب فایل
          <input type="file" accept="application/pdf" multiple onChange={handleInput} hidden />
        </label>
      </div>

      {items.length > 0 && (
        <section className="upload-queue">
          <div className="queue-header">
            <h2>صف آپلود</h2>
            <button className="primary-button" onClick={uploadAll}>
              شروع آپلود
            </button>
          </div>
          {items.map((item) => (
            <article key={item.id} className="upload-row">
              <FileUp size={20} />
              <div>
                <strong>{item.file.name}</strong>
                <span>{(item.file.size / 1024 / 1024).toFixed(2)} MB</span>
              </div>
              <div className={`upload-state state-${item.status}`}>
                {item.status === 'uploading' && <Loader2 className="spin" size={18} />}
                {item.status === 'done' && <CheckCircle2 size={18} />}
                <span>
                  {item.status === 'waiting'
                    ? 'در انتظار'
                    : item.status === 'uploading'
                      ? 'در حال آپلود'
                      : item.status === 'done'
                        ? 'انجام شد'
                        : 'خطا'}
                </span>
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
