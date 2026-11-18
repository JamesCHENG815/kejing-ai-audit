export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

/**
 * 访问令牌：必须与 backend/.env 中的 APP_AUTH_TOKEN 一致。
 * 留空时后端只允许本机访问，本地开发可以完全不配置。
 */
export const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN?.trim() ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

export function authHeaders(): Record<string, string> {
  return API_TOKEN ? { "X-API-Token": API_TOKEN } : {};
}

/**
 * 给 <audio src> 这类无法自定义请求头的 URL 带上令牌。
 * 这是唯一允许令牌出现在查询串里的场景。
 */
export function withToken(url: string): string {
  if (!API_TOKEN) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(API_TOKEN)}`;
}

async function errorFrom(response: Response, fallback: string) {
  const body = await response.json().catch(() => null);
  return new ApiError(
    body?.detail ?? `${fallback}（HTTP ${response.status}）`,
    response.status,
  );
}

export async function apiRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw await errorFrom(response, "请求失败");
  }

  // 删除接口返回 204，没有响应体，直接解析 JSON 会抛错。
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      return null;
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() ?? null;
}

/**
 * 带令牌下载文件。
 * 不能再直接用 <a href>：那样浏览器发不出自定义请求头，会拿到 401。
 */
export async function downloadFile(path: string, fallbackName: string) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw await errorFrom(response, "下载失败");
  }
  const blob = await response.blob();
  const filename =
    filenameFromDisposition(response.headers.get("Content-Disposition")) ??
    fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // 立刻 revoke 会让部分浏览器丢掉下载，延后释放。
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  return filename;
}

export function uploadWithProgress<T>(
  path: string,
  formData: FormData,
  onProgress: (progress: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}${path}`);
    request.responseType = "json";
    if (API_TOKEN) {
      request.setRequestHeader("X-API-Token", API_TOKEN);
    }
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onerror = () =>
      reject(
        new ApiError(
          `无法连接后端服务（${API_BASE_URL}），请确认 FastAPI 已启动`,
        ),
      );
    request.ontimeout = () => reject(new ApiError("上传超时，请检查后端服务后重试"));
    request.timeout = 120_000;
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        resolve(request.response as T);
        return;
      }
      reject(
        new ApiError(
          request.response?.detail ?? `上传失败（HTTP ${request.status}）`,
          request.status,
        ),
      );
    };
    request.send(formData);
  });
}
