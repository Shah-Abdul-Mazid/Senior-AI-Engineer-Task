export interface ApiResponse<T = any> {
  data: T;
  status: 'success' | 'error';
  message?: string;
  metadata?: {
    latencyMs?: number;
    tokensUsed?: number;
    timestamp?: string;
  };
}

export interface ApiError {
  detail: string;
  code: string;
  status: number;
  fieldErrors?: Record<string, string[]>;
}

export interface TaskStatusResponse<T = any> {
  taskId: string;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  progress: number;
  result?: T;
  error?: string;
  createdAt?: string;
  updatedAt?: string;
}
