export interface Project {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  file_count?: number;
  run_count?: number;
}

export interface UploadedFile {
  id: string;
  project_id: string;
  original_filename: string;
  stored_filename: string;
  role: 'source' | 'target' | 'unassigned';
  file_size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  encoding: string | null;
  delimiter: string | null;
  has_bom: boolean;
  columns_json: Record<string, string>;
  parse_warnings_json: string[];
  status: 'uploaded' | 'inspected' | 'error';
  error_message: string | null;
  uploaded_at: string;
}

export interface FieldMapping {
  source_columns: string[];
  target_column: string;
  data_type: 'string' | 'numeric' | 'date';
  transform: 'none' | 'upper' | 'lower';
  required: boolean;
  is_matching_key: boolean;
  compare_in_validation: boolean;
}

export interface Normalization {
  trim: boolean;
  case_insensitive: boolean;
  null_tokens: string[];
  numeric_normalize: boolean;
  date_normalize: boolean;
}

export interface MappingConfig {
  id: string;
  project_id: string;
  name: string;
  source_file_id: string;
  target_file_id: string;
  column_mappings_json: FieldMapping[];
  normalization_json: Normalization;
  validation_rules_json: Record<string, boolean>;
  created_at: string;
  updated_at: string;
}

export interface MappingSuggestion {
  source_column: string;
  target_column: string;
  confidence: number;
  reason: string;
}

export interface ValidationRun {
  id: string;
  project_id: string;
  mapping_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress_percent: number;
  current_operation: string | null;
  error_message: string | null;
  summary_json: Record<string, number>;
  result_dir: string | null;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface MappingTemplate {
  id: string;
  project_id: string | null;
  name: string;
  description?: string | null;
  column_mappings_json: FieldMapping[];
  normalization_json: Normalization;
  validation_rules_json: Record<string, boolean>;
  created_at: string;
}

export interface ResultsPage {
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
}
