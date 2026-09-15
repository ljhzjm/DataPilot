export interface DatasetColumn {
  name: string
  data_type: string
  nullable: boolean
}

export interface Dataset {
  id: string
  name: string
  original_filename: string
  table_name: string
  file_type: string
  file_size: number
  status: 'processing' | 'ready' | 'failed'
  row_count: number | null
  columns: DatasetColumn[]
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DatasetSummary {
  id: string
  name: string
  original_filename: string
  table_name: string
  file_type: string
  file_size: number
  status: 'processing' | 'ready' | 'failed'
  row_count: number | null
  created_at: string
  updated_at: string
}

