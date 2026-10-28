export type TemplateMode =
  | 'all'
  | 'streaming'
  | 'rag'
  | 'document'
  | 'canvas'
  | 'analytics'
  | 'mlops';

export interface TemplateConfig {
  mode: TemplateMode;
  appName: string;
}

export const TEMPLATE_CONFIG: TemplateConfig = {
  mode: 'document',
  appName: 'AI-Powered Document Intelligence System',
};
