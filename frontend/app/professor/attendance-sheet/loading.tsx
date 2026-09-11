import { AttendanceSheetSkeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div className="min-h-screen bg-background p-container-padding">
      <AttendanceSheetSkeleton />
    </div>
  );
}
