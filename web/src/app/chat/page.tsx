import { NotBuiltYet } from "@/components/ui/not-built";

export default function ChatPage() {
  return (
    <NotBuiltYet
      category="Ask"
      pr="PR 5"
      headline="Ask your notes, get the paragraph back."
      what="Answers stream token by token and carry a citation to the chunk they came from. When your material does not cover the question, it says so rather than answering from general knowledge."
    />
  );
}
