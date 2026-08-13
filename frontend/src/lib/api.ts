export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
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
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      body?.detail ?? `请求失败（HTTP ${response.status}）`,
      response.status,
    );
  }

  return response.json() as Promise<T>;
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
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onerror = () => reject(new ApiError("无法连接后端服务"));
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
