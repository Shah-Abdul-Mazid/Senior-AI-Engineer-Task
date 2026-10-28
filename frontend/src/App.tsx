import { useState, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import DocumentIntelligenceStudio from '@/components/document/DocumentIntelligenceStudio';

export default function App() {
  const [docCount, setDocCount] = useState<number>(0);

  const handleQueueCountChange = useCallback((count: number) => {
    setDocCount(count);
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0B0B0E] text-gray-100 overflow-hidden font-sans">
      {/* Clean Global Header */}
      <Header documentCount={docCount} />

      {/* Main Document Intelligence Studio Workspace */}
      <main className="flex-1 overflow-hidden p-3 md:p-4 bg-[#0D0D11]">
        <DocumentIntelligenceStudio onQueueCountChange={handleQueueCountChange} />
      </main>
    </div>
  );
}
