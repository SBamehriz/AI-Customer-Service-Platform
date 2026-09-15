import { useSession } from '@/app/session';
import AgentHome from './AgentHome';
import SupervisorHome from './SupervisorHome';

/** Home is a different page per role, not one page with pieces hidden. */
export default function HomePage() {
  const { user } = useSession();
  return user?.role === 'agent' ? <AgentHome /> : <SupervisorHome />;
}
