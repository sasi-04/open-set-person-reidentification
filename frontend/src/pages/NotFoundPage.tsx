import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";

export default function NotFoundPage() {
  return (
    <EmptyState icon={<Compass aria-hidden className="size-5" />} title="This page does not exist" action={<Link to="/"><Button variant="primary">Go to the Command Center</Button></Link>}>
      Use the navigation to pick one of the seven screens.
    </EmptyState>
  );
}
