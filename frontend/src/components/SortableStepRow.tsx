"use client";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

interface SortableStepRowProps {
  id: string;
  // The handle is hidden and dragging is off for people who may not reorder, or while something is saving.
  canDrag: boolean;
  children: React.ReactNode;
}

// One step in the list that can be dragged to a new place. Only the handle starts a drag,
// so the buttons inside the row (Edit, Delete) still work with a normal click.
export default function SortableStepRow({ id, canDrag, children }: SortableStepRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: id,
    disabled: !canDrag,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition: transition,
    // The row being dragged sits above the others and is slightly see-through.
    zIndex: isDragging ? 10 : undefined,
    opacity: isDragging ? 0.7 : 1,
  };

  return (
    <li ref={setNodeRef} style={style} className="flex items-stretch gap-2 rounded-xl border border-white/10 bg-[#0a0e1a] p-4">
      {canDrag ? (
        <button
          type="button"
          aria-label="Drag to change this step's place"
          title="Drag to change this step's place"
          {...attributes}
          {...listeners}
          className="flex w-6 flex-shrink-0 cursor-grab touch-none items-center justify-center rounded text-gray-500 hover:bg-white/5 hover:text-gray-300 active:cursor-grabbing"
        >
          ⠿
        </button>
      ) : null}
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  );
}
