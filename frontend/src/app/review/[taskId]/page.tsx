import ReviewDetail from "./review-detail";

type ReviewDetailPageProps = {
  params: Promise<{ taskId: string }>;
};

export default async function ReviewDetailPage({ params }: ReviewDetailPageProps) {
  const { taskId } = await params;
  return <ReviewDetail taskId={taskId} />;
}
