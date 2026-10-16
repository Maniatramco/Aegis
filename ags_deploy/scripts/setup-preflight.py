"""Read-only adapter for workstation prerequisite setup. Never builds/publishes."""
import argparse
import json
from pathlib import Path
import sys
import release_cli as cli


class SetupWorkflow(cli.Workflow):
    def approve_connection(self):
        print('Prerequisite setup also verifies the selected image registry. '
              'After preflight it may request Docker login using existing credentials; '
              'no image build, push, database DDL or workload update is performed.')
        super().approve_connection()


def run_preflight(inputs, output, workflow_factory=SetupWorkflow, working_tree=False):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation refuses to overwrite a target file or previous receipt.
    with output.open('x', encoding='utf-8') as report:
        workflow = None
        try:
            workflow = workflow_factory(cli.load_inputs(Path(inputs)), check_only=True)
            workflow.working_tree = working_tree
            result = workflow.run()
            if (result.get('state') != 'preflight-only' or result.get('database_installed')
                    or result.get('builds') != 'Not run' or result.get('publication') != 'Not attempted'):
                raise cli.DeploymentStopped('Setup did not return an unchanged preflight-only result')
            payload = {'state': 'preflight-only', 'preflight': result,
                       'registry': getattr(workflow, 'registry', None),
                       'registry_namespace': getattr(workflow, 'registry_namespace', None)}
            json.dump(payload, report, indent=2)
            return 0
        except (Exception, KeyboardInterrupt) as error:
            json.dump({'state': 'stopped', 'error': type(error).__name__,
                       'preflight': getattr(workflow, 'record', {})}, report, indent=2)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--working-tree', action='store_true', help='Check a snapshot of saved local source instead of JSON Ref')
    args = parser.parse_args()
    try:
        return run_preflight(args.inputs, args.output, working_tree=args.working_tree)
    except (KeyboardInterrupt, EOFError):
        print('Prerequisite preflight cancelled; inspect the saved setup report.', file=sys.stderr)
        return 130
    except Exception as error:
        safe = (cli.DeploymentStopped, cli.ORACLE_RELEASE.OracleReleaseError,
                cli.GUARD.ReleaseCheckError, cli.SCHEMA.SchemaMismatch)
        detail = str(error) if isinstance(error, safe) else type(error).__name__
        print('Prerequisite preflight stopped: '+detail, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
