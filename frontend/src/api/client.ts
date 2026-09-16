import axios from 'axios';
import type {
  Project, UploadedFile, MappingConfig, MappingSuggestion,
  ValidationRun, MappingTemplate, ResultsPage, FieldMapping, Normalization,
} from '../types';

export const api = axios.create({ baseURL: '/api' });

// Surface backend's friendly {detail:{message}} shape as a plain Error message
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const msg =
      err?.response?.data?.detail?.message ||
      err?.response?.data?.detail ||
      err?.message ||
      'Something went wrong.';
    return Promise.reject(new Error(msg));
  }
);

// ---- Projects ----
export const listProjects = () => api.get<Project[]>('/projects').then((r) => r.data);
export const createProject = (name: string, description?: string) =>
  api.post<Project>('/projects', { name, description }).then((r) => r.data);
export const getProject = (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data);
export const deleteProject = (id: string) => api.delete(`/projects/${id}`).then((r) => r.data);

// ---- Files ----
export const listFiles = (projectId: string) =>
  api.get<UploadedFile[]>(`/projects/${projectId}/files`).then((r) => r.data);

export const uploadFile = (projectId: string, file: File, onProgress?: (pct: number) => void) => {
  const form = new FormData();
  form.append('file', file);
  return api
    .post<UploadedFile>(`/projects/${projectId}/files`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        if (onProgress && evt.total) onProgress(Math.round((evt.loaded / evt.total) * 100));
      },
    })
    .then((r) => r.data);
};

export const setFileRole = (projectId: string, fileId: string, role: string) =>
  api.patch<UploadedFile>(`/projects/${projectId}/files/${fileId}/role`, { role }).then((r) => r.data);

export const previewFile = (projectId: string, fileId: string, rows = 50) =>
  api
    .get<{ columns: Record<string, string>; rows: Record<string, unknown>[]; row_count: number; warnings: string[] }>(
      `/projects/${projectId}/files/${fileId}/preview`,
      { params: { rows } }
    )
    .then((r) => r.data);

export const deleteFile = (projectId: string, fileId: string) =>
  api.delete(`/projects/${projectId}/files/${fileId}`).then((r) => r.data);

// ---- Mapping suggestions ----
export const getMappingSuggestions = (projectId: string, sourceFileId: string, targetFileId: string) =>
  api
    .get<{ source_columns: Record<string, string>; target_columns: Record<string, string>; suggestions: MappingSuggestion[] }>(
      `/projects/${projectId}/mapping-suggestions`,
      { params: { source_file_id: sourceFileId, target_file_id: targetFileId } }
    )
    .then((r) => r.data);

// ---- Mappings ----
export const listMappings = (projectId: string) =>
  api.get<MappingConfig[]>(`/projects/${projectId}/mappings`).then((r) => r.data);

export const createMapping = (
  projectId: string,
  payload: { name: string; source_file_id: string; target_file_id: string; column_mappings: FieldMapping[]; normalization: Normalization }
) => api.post<MappingConfig>(`/projects/${projectId}/mappings`, payload).then((r) => r.data);

export const updateMapping = (
  projectId: string,
  mappingId: string,
  payload: Partial<{ name: string; column_mappings: FieldMapping[]; normalization: Normalization; validation_rules: Record<string, boolean> }>
) => api.patch<MappingConfig>(`/projects/${projectId}/mappings/${mappingId}`, payload).then((r) => r.data);

export const deleteMapping = (projectId: string, mappingId: string) =>
  api.delete(`/projects/${projectId}/mappings/${mappingId}`).then((r) => r.data);

// ---- Mapping templates ----
export const listTemplates = (projectId?: string) =>
  api.get<MappingTemplate[]>('/mapping-templates', { params: projectId ? { project_id: projectId } : {} }).then((r) => r.data);

export const createTemplate = (payload: {
  name: string; description?: string; project_id?: string;
  column_mappings: FieldMapping[]; normalization: Normalization;
}) => api.post<MappingTemplate>('/mapping-templates', payload).then((r) => r.data);

export const duplicateTemplate = (id: string) => api.post<MappingTemplate>(`/mapping-templates/${id}/duplicate`).then((r) => r.data);
export const deleteTemplate = (id: string) => api.delete(`/mapping-templates/${id}`).then((r) => r.data);

// ---- Validation runs ----
export const listRuns = (projectId: string) =>
  api.get<ValidationRun[]>(`/projects/${projectId}/runs`).then((r) => r.data);

export const startRun = (projectId: string, mappingId: string) =>
  api.post<ValidationRun>(`/projects/${projectId}/runs`, { mapping_id: mappingId }).then((r) => r.data);

export const getRun = (projectId: string, runId: string) =>
  api.get<ValidationRun>(`/projects/${projectId}/runs/${runId}`).then((r) => r.data);

export const compareRuns = (projectId: string, runIdA: string, runIdB: string) =>
  api.get(`/projects/${projectId}/runs/${runIdA}/compare/${runIdB}`).then((r) => r.data);

// ---- Results ----
export const getTabResults = (
  projectId: string,
  runId: string,
  tab: string,
  params: { page?: number; page_size?: number; search?: string; sort_by?: string; sort_dir?: string }
) => api.get<ResultsPage>(`/projects/${projectId}/runs/${runId}/results/${tab}`, { params }).then((r) => r.data);

export const getRecordDetail = (projectId: string, runId: string, matchingKey: string) =>
  api.get(`/projects/${projectId}/runs/${runId}/results/record/${encodeURIComponent(matchingKey)}`).then((r) => r.data);

// ---- Export ----
export const exportExcelUrl = (projectId: string, runId: string) => `/api/projects/${projectId}/runs/${runId}/export/excel`;
export const exportCsvUrl = (projectId: string, runId: string, tab: string) =>
  `/api/projects/${projectId}/runs/${runId}/export/csv/${tab}`;
