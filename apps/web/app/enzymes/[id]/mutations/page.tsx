import MutationKnowledgeClient from "./MutationKnowledgeClient";

type MutationKnowledgePageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function MutationKnowledgePage({ params }: MutationKnowledgePageProps) {
  const { id } = await params;

  return <MutationKnowledgeClient enzymeId={id} />;
}
