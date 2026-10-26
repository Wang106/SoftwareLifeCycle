import ProductionCorrectionHistory from '../../../../../../components/production-correction-history';
export default async function Page({ params }: { params: Promise<{ id: string; changeoverNo: string }> }) {
  const { id, changeoverNo } = await params;
  return ProductionCorrectionHistory({ kind: 'changeover', deploymentNo: id, recordNo: changeoverNo });
}
