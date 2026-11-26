import { spawnSync } from 'node:child_process';

export async function withDatabaseUnavailable<T>(
  project: string,
  service: 'orders' | 'support',
  operation: () => Promise<T>,
): Promise<T> {
  if (!new RegExp(`^nivaro-${service}-qa-[a-f0-9]{8}$`).test(project)) {
    throw new Error(`Disposable ${service} database required`);
  }
  const database = service === 'orders' ? 'nivaro_orders' : 'nivaro_support';
  const execute = (sql: string) => {
    const result = spawnSync('docker', [
      'exec', `${project}-postgres-1`, 'psql', '-X', '-U', 'postgres', '-d', 'postgres',
      '-At', '-v', 'ON_ERROR_STOP=1', '-c', sql,
    ], { encoding: 'utf8', timeout: 15_000 });
    if (result.status !== 0) throw new Error(`PostgreSQL outage fixture failed for ${service}: ${result.stderr || result.error}`);
    return result.stdout.trim();
  };

  try {
    execute(`ALTER DATABASE ${database} ALLOW_CONNECTIONS false`);
    const clientSessions = `pg_stat_activity WHERE datname = '${database}' AND backend_type = 'client backend'`;
    execute(`SELECT pg_terminate_backend(pid, 5000) FROM ${clientSessions}`);
    if (execute(`SELECT count(*) FROM ${clientSessions}`) !== '0') {
      throw new Error(`Could not disconnect all ${service} database sessions`);
    }
    return await operation();
  } finally {
    execute(`ALTER DATABASE ${database} ALLOW_CONNECTIONS true`);
  }
}
