import { Skeleton } from "@/components/ui/skeleton";

export function MovieCardSkeleton() {
  return (
    <div
      className="flex flex-col overflow-hidden rounded-lg"
      style={{
        backgroundColor: "var(--card)",
        borderWidth: 1,
        borderColor: "var(--border)",
      }}
    >
      <Skeleton className="aspect-[2/3] w-full rounded-none" />
      <div className="flex flex-col gap-2 p-3">
        <Skeleton className="h-4 w-[85%]" />
        <Skeleton className="h-3 w-[55%]" />
        <div className="flex gap-1">
          <Skeleton className="h-4 w-12 rounded-full" />
          <Skeleton className="h-4 w-10 rounded-full" />
        </div>
        <Skeleton className="h-3 w-8 mt-1" />
      </div>
    </div>
  );
}
