import * as React from 'react';
import { Page, PageHeader } from '@/components/layout';
import { EmptyState, SegmentedControl } from '@/components/ui';
import { Lock } from '@/components/icons';
import { useCanManage } from '@/app/session';
import { WorkspaceSettings } from './WorkspaceSettings';
import { AiSettings } from './AiSettings';
import { DataSettings } from './DataSettings';
import { TeamSettings } from './TeamSettings';
import { ChannelSettings } from './ChannelSettings';
import { AutomationSettings } from './AutomationSettings';
import { DeveloperSettings } from './DeveloperSettings';

type Tab = 'workspace' | 'team' | 'channels' | 'ai' | 'automation' | 'data' | 'developer';

const TABS: { value: Tab; label: string }[] = [
  { value: 'workspace', label: 'Workspace' },
  { value: 'team', label: 'Team' },
  { value: 'channels', label: 'Channels' },
  { value: 'ai', label: 'AI' },
  { value: 'automation', label: 'Automation' },
  { value: 'data', label: 'Data' },
  { value: 'developer', label: 'Developer' },
];

const MANAGER_ONLY: Tab[] = ['team', 'channels', 'ai', 'automation', 'data', 'developer'];

export default function SettingsPage() {
  const canManage = useCanManage();
  const [tab, setTab] = React.useState<Tab>('workspace');
  const locked = !canManage && MANAGER_ONLY.includes(tab);

  return (
    <Page className="space-y-4">
      <PageHeader
        title="Settings"
        description="Your team, your channels, your model, your data."
        actions={
          <SegmentedControl
            aria-label="Settings section"
            options={TABS}
            value={tab}
            onChange={setTab}
          />
        }
      />

      {locked ? (
        <EmptyState
          icon={<Lock className="h-5 w-5" />}
          title="Supervisors only"
          description="This section changes the whole workspace, so it is limited to supervisors and owners. Ask one of them if you need something here."
        />
      ) : (
        <>
          {tab === 'workspace' ? <WorkspaceSettings /> : null}
          {tab === 'team' ? <TeamSettings /> : null}
          {tab === 'channels' ? <ChannelSettings /> : null}
          {tab === 'ai' ? <AiSettings /> : null}
          {tab === 'automation' ? <AutomationSettings /> : null}
          {tab === 'data' ? <DataSettings /> : null}
          {tab === 'developer' ? <DeveloperSettings /> : null}
        </>
      )}
    </Page>
  );
}
