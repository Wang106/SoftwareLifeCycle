import ProductionCorrectionHistory from '../../../../../../components/production-correction-history';
export default async function Page({ params }: { params: Promise<{ id: string; batchNo: string }> }) {
  const { id, batchNo } = await params;
  return ProductionCorrectionHistory({ kind: 'batch', deploymentNo: id, recordNo: batchNo });
}
