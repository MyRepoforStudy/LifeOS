import { useState } from "react";
import { useSearchParams } from "react-router";

import { useQuests } from "../api/queries";
import { QUEST_TYPES, type QuestType } from "../api/types";
import { Icon } from "../components/Icon";
import { QuestForm } from "../components/QuestForm";
import { QuestRow } from "../components/QuestRow";
import { useI18n } from "../i18n";

function isQuestType(value: string | null): value is QuestType {
  return value !== null && (QUEST_TYPES as string[]).includes(value);
}

export function QuestsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const typeParam = params.get("type");
  const questType: QuestType = isQuestType(typeParam) ? typeParam : "daily";
  const { data, isLoading } = useQuests({ quest_type: questType });
  const [creating, setCreating] = useState(false);

  return (
    <main className="page">
      <div className="page-header">
        <h1>{t("nav.quests")}</h1>
        <button className="btn btn-primary btn-small" onClick={() => setCreating(true)}>
          <Icon name="plus" />
          {t("quest.newQuest")}
        </button>
      </div>

      <div className="segmented" role="tablist" style={{ marginBottom: 14 }}>
        {QUEST_TYPES.map((type) => (
          <button
            key={type}
            role="tab"
            aria-pressed={type === questType}
            aria-selected={type === questType}
            onClick={() => setParams({ type }, { replace: true })}
          >
            {t(`questTypeTab.${type}`)}
          </button>
        ))}
      </div>

      <div className="card flush">
        {isLoading && <div className="skeleton" style={{ height: 220, margin: 6 }} />}
        {data && data.items.length === 0 && (
          <div className="empty">
            <Icon name="target" />
            <strong>{t("quest.empty")}</strong>
            <p className="muted small">{t("quest.emptyHint")}</p>
            <button className="btn btn-small" style={{ marginTop: 6 }} onClick={() => setCreating(true)}>
              <Icon name="plus" />
              {t("quest.newQuest")}
            </button>
          </div>
        )}
        {data && data.items.length > 0 && (
          <div className="quest-list">
            {data.items.map((quest) => (
              <QuestRow key={quest.id} quest={quest} />
            ))}
          </div>
        )}
      </div>

      {creating && <QuestForm initialType={questType} onClose={() => setCreating(false)} />}
    </main>
  );
}
