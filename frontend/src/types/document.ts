export interface ExtractedLineItem {
  id: string;
  description: string;
  quantity: number;
  unitPrice: number;
  amount: number;
  matchedWithExcel?: boolean;
}

export interface ExtractedInvoice {
  id: string;
  fileName: string;
  pageCount: number;
  invoiceNumber: string;
  invoiceDate: string;
  supplierName: string;
  customerName: string;
  currency: string;
  subtotal: number;
  tax: number;
  total: number;
  confidenceScore: number;
  status: 'VERIFIED' | 'MATH_DISCREPANCY' | 'MANUAL_REVIEW';
  lineItems: ExtractedLineItem[];
}

export interface ReconciliationRow {
  field: string;
  pdfValue: string | number;
  excelValue: string | number;
  isMatch: boolean;
  delta?: string | number;
}
