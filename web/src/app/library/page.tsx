import { NotBuiltYet } from "@/components/ui/not-built";

export default function LibraryPage() {
  return (
    <NotBuiltYet
      category="Library"
      pr="PR 4"
      headline="Your material, chunked and searchable."
      what="Upload notes, slides and PDFs. Each document is split with token-aware overlap so a retrieved chunk is never a sentence cut in half, then embedded and scoped to your account."
    />
  );
}
