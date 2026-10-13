/**
 * Model & System Settings (screen G).
 *
 * In plain words: everything about HOW the system is set up, on three tabs -
 *   Model & thresholds   the loaded models and the versioned decision policy (validated settings, plus
 *                        clearly marked experimental changes)
 *   Runtime & system     live health of each component, limits, datasets, loading errors
 *   Access, appearance   who you are, theme, privacy/retention, the audit trail and the honest limits
 * The tab can be chosen from a link (``/settings?tab=system``) so other screens can point straight at it.
 */
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { ModelPanel } from "@/features/model/ModelPanel";
import { PreferencesPanel } from "@/features/settings/PreferencesPanel";
import { SystemPanel } from "@/features/settings/SystemPanel";

const TAB_IDS = ["model", "system", "preferences"] as const;

export default function SettingsPage() {
  const [params] = useSearchParams();
  const requested = params.get("tab");
  const initial = TAB_IDS.find((id) => id === requested) ?? "model";
  return (
    <>
      <PageHeader title="Model & system settings" description="The loaded models, the decision rules and how far they can be trusted, the health of the runtime, and how data is kept." />
      <Tabs
        initial={initial}
        tabs={[
          { id: "model", label: "Model & thresholds", content: <ModelPanel /> },
          { id: "system", label: "Runtime & system", content: <SystemPanel /> },
          { id: "preferences", label: "Access, appearance & privacy", content: <PreferencesPanel /> },
        ]}
      />
    </>
  );
}
