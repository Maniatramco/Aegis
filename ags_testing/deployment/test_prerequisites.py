"""Offline prerequisite automation checks. Installers/OCI/Docker are simulated."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT/'ags_deploy/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('setup_preflight', SCRIPTS/'setup-preflight.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def literal(value):
    return "'"+str(value).replace("'", "''")+"'"


class PreflightAdapterTests(unittest.TestCase):
    def fixture(self, base):
        path = base/'inputs.json'
        path.write_text(json.dumps({'DB_Object':'N','DeployFrontend':'Y','DeployBackend':'Y'}))
        return path

    def test_adapter_always_requests_check_only_and_exports_exact_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            calls = []
            class Fake:
                registry = 'registry.invalid'
                registry_namespace = 'test'
                def __init__(self, values, check_only):
                    calls.append(check_only)
                    self.record = {'state':'preflight-only','database_installed':False,
                                   'builds':'Not run','publication':'Not attempted'}
                def run(self): return self.record
            output = base/'report.json'
            self.assertEqual(adapter.run_preflight(self.fixture(base), output, Fake), 0)
            self.assertEqual(calls, [True])
            self.assertEqual(json.loads(output.read_text())['registry'], 'registry.invalid')

    def test_existing_result_is_never_overwritten_or_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base/'report.json'
            output.write_text('existing evidence')
            with self.assertRaises(FileExistsError):
                adapter.run_preflight(self.fixture(base), output, lambda *a,**k:self.fail('workflow started'))
            self.assertEqual(output.read_text(), 'existing evidence')

    def test_adapter_rejects_publication_and_does_not_record_sensitive_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            class Fake:
                def __init__(self, values, check_only):
                    self.record = {'state':'preflight-only','database_installed':False,
                                   'builds':'images built','publication':'attempted'}
                def run(self): return self.record
            with self.assertRaises(adapter.cli.DeploymentStopped):
                adapter.run_preflight(self.fixture(base), base/'unsafe.json', Fake)
            class Failed:
                def __init__(self, values, check_only): self.record = {'state':'stopped'}
                def run(self): raise RuntimeError('DO-NOT-RECORD-PRIVATE-PASSWORD')
            with self.assertRaises(RuntimeError):
                adapter.run_preflight(self.fixture(base), base/'failed.json', Failed)
            self.assertNotIn('DO-NOT-RECORD', (base/'failed.json').read_text())


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell'), 'Windows PowerShell prerequisite tests')
class PowerShellPrerequisiteTests(unittest.TestCase):
    def run_ps(self, base, body, operator_input=''):
        harness = base/'harness.ps1'
        harness.write_text("$ErrorActionPreference='Stop'\n. "+literal(SCRIPTS/'deployment-environment.ps1')+
                           "\n. "+literal(SCRIPTS/'setup-prerequisites.ps1')+"\n"+body, encoding='utf-8-sig')
        return subprocess.run([shutil.which('powershell'), '-NoLogo','-NoProfile','-File',str(harness)],
                              input=operator_input, text=True, capture_output=True, timeout=35, cwd=base)

    def test_shortcuts_forward_alternate_target_before_changing_directory(self):
        for name in ('Deploy-Aegis.ps1','Check-Aegis.ps1'):
            with self.subTest(script=name), tempfile.TemporaryDirectory(prefix='aegis destinations ') as temporary:
                base=Path(temporary)
                deploy=base/'checkout with spaces'/'ags_deploy'
                deploy.mkdir(parents=True)
                shutil.copyfile(ROOT/'ags_deploy'/name,deploy/name)
                (deploy/'aegis-oci-inputs.json').write_text('{"default":"must not be selected"}')
                (deploy/'deploy.ps1').write_text(
                    "param([string]$Inputs,[switch]$CheckOnly)\n"
                    "@{Inputs=$Inputs;CheckOnly=[bool]$CheckOnly}|ConvertTo-Json|Set-Content -LiteralPath $env:AEGIS_TEST_WRAPPER_CAPTURE\n",
                    encoding='utf-8-sig')
                selected=base/'other target.json'
                selected.write_text('{}')
                output=base/'captured.json'
                result=self.run_ps(base,"$env:AEGIS_TEST_WRAPPER_CAPTURE="+literal(output)+"\n& "+
                    literal(deploy/name)+" -Inputs '.\\other target.json'\n")
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                captured=json.loads(output.read_text(encoding='utf-8-sig'))
                self.assertEqual(Path(captured['Inputs']),selected)
                self.assertEqual(captured['CheckOnly'],name=='Check-Aegis.ps1')
                self.assertIn(str(selected),result.stdout)

    def test_deploy_default_still_uses_adjacent_json_and_missing_target_stops(self):
        with tempfile.TemporaryDirectory(prefix='aegis destinations ') as temporary:
            base=Path(temporary)
            deploy=base/'checkout'/'ags_deploy'
            deploy.mkdir(parents=True)
            shutil.copyfile(ROOT/'ags_deploy/Deploy-Aegis.ps1',deploy/'Deploy-Aegis.ps1')
            default=deploy/'aegis-oci-inputs.json'
            default.write_text('{}')
            (deploy/'deploy.ps1').write_text(
                "param([string]$Inputs)\n$Inputs|Set-Content -LiteralPath $env:AEGIS_TEST_WRAPPER_CAPTURE\n",
                encoding='utf-8-sig')
            output=base/'captured.txt'
            result=self.run_ps(base,"$env:AEGIS_TEST_WRAPPER_CAPTURE="+literal(output)+"\n& "+literal(deploy/'Deploy-Aegis.ps1')+"\n")
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(Path(output.read_text(encoding='utf-8-sig').strip()),default)
            result=self.run_ps(base,"$env:AEGIS_TEST_WRAPPER_CAPTURE="+literal(base/'should-not-exist.txt')+
                "\n& "+literal(deploy/'Deploy-Aegis.ps1')+" -Inputs '.\\missing.json'\n")
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((base/'should-not-exist.txt').exists())

    def test_setup_prints_matching_deploy_command_for_alternate_destination(self):
        with tempfile.TemporaryDirectory(prefix='aegis destinations ') as temporary:
            base=Path(temporary)
            deploy=base/'checkout'/'ags_deploy'
            (deploy/'scripts').mkdir(parents=True)
            shutil.copyfile(ROOT/'ags_deploy/Setup-Aegis.ps1',deploy/'Setup-Aegis.ps1')
            (deploy/'scripts/deployment-environment.ps1').write_text('# offline fixture')
            (deploy/'scripts/setup-prerequisites.ps1').write_text(
                "function Invoke-AegisPrerequisites { param($DeploymentRoot,$Inputs,$InstallMissing)\n"
                "@{Inputs=$Inputs}|ConvertTo-Json|Set-Content -LiteralPath $env:AEGIS_TEST_WRAPPER_CAPTURE\n"
                "return [pscustomobject]@{ReportPath='offline-report.json'} }\n",encoding='utf-8-sig')
            selected=base/"colleague's OCI.json"
            selected.write_text('{}')
            output=base/'captured.json'
            result=self.run_ps(base,"$env:AEGIS_TEST_WRAPPER_CAPTURE="+literal(output)+"\n& "+
                literal(deploy/'Setup-Aegis.ps1')+' -Inputs '+literal(selected.name)+"\n")
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(Path(json.loads(output.read_text(encoding='utf-8-sig'))['Inputs']),selected)
            self.assertIn('AEGIS_PREREQUISITES_READY',result.stdout)
            expected="& "+literal(deploy/'Deploy-Aegis.ps1')+' -Inputs '+literal(selected)
            self.assertIn(expected,result.stdout)

    def test_native_failure_is_not_silently_converted_to_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_ps(Path(temporary), "$r=Invoke-AegisNative "+literal(sys.executable)+
                " @('-B','-c','raise SystemExit(7)') -Capture -AllowFailure\n"
                "if($r.ExitCode -ne 7){throw 'Exit code lost'}\n"
                "try { $null=Invoke-AegisNative "+literal(sys.executable)+
                " @('-B','-c','raise SystemExit(9)') -Capture; throw 'FAILED-TO-STOP' }\n"
                "catch { if($_.Exception.Message -match 'FAILED-TO-STOP'){throw}; 'EXPECTED-NATIVE-STOP' }\n")
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('EXPECTED-NATIVE-STOP', result.stdout)

    def test_streamed_native_output_stays_visible_when_result_is_discarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_ps(Path(temporary), "$null=Invoke-AegisNative "+literal(sys.executable)+
                " @('-B','-c',\"print('VISIBLE-OPERATOR-OUTPUT')\")\n"
                "$r=Invoke-AegisNative "+literal(sys.executable)+
                " @('-B','-c','raise SystemExit(6)') -AllowFailure\n"
                "if($r.ExitCode -ne 6){throw 'Streamed exit code lost'}\n")
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('VISIBLE-OPERATOR-OUTPUT',result.stdout)

    def test_streamed_native_approval_prompt_accepts_operator_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_ps(Path(temporary), "$null=Invoke-AegisNative "+literal(sys.executable)+
                " @('-u','-B','-c',\"answer=input('OFFLINE-APPROVAL-PROMPT: '); print('RECEIVED:'+answer)\")\n",
                operator_input='CONNECT\n')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('OFFLINE-APPROVAL-PROMPT:',result.stdout)
            self.assertIn('RECEIVED:CONNECT',result.stdout)

    def test_approval_prompt_is_visible_before_any_operator_input(self):
        with tempfile.TemporaryDirectory(prefix='aegis prompt ') as temporary:
            base=Path(temporary)
            child=base/'interactive probe.py'
            child.write_text("answer=input('OFFLINE-LIVE-PROMPT: '); print('RECEIVED:'+answer)\n")
            harness=base/'prompt harness.ps1'
            harness.write_text("$ErrorActionPreference='Stop'\n. "+literal(SCRIPTS/'setup-prerequisites.ps1')+
                "\n$null=Invoke-AegisNative "+literal(sys.executable)+" @('-u','-B',"+literal(child)+")\n",
                encoding='utf-8-sig')
            process=subprocess.Popen([shutil.which('powershell'),'-NoLogo','-NoProfile','-File',str(harness)],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,cwd=base)
            observed=bytearray()
            prompt=threading.Event()
            def read_output():
                while True:
                    value=process.stdout.read(1)
                    if not value: break
                    observed.extend(value)
                    if b'OFFLINE-LIVE-PROMPT: ' in observed: prompt.set()
            reader=threading.Thread(target=read_output,daemon=True)
            reader.start()
            try:
                visible=prompt.wait(8)
                process.stdin.write(b'CONNECT\n' if visible else b'\n')
                process.stdin.close()
                process.wait(timeout=10)
                reader.join(timeout=3)
                errors=process.stderr.read().decode(errors='replace')
                self.assertTrue(visible,'Approval prompt was buffered until input/exit: '+observed.decode(errors='replace')+errors)
                self.assertEqual(process.returncode,0,errors)
                self.assertIn(b'RECEIVED:CONNECT',observed)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                for stream in (process.stdin,process.stdout,process.stderr):
                    if not stream.closed: stream.close()

    def test_interactive_process_preserves_windows_arguments_and_powershell_directory(self):
        with tempfile.TemporaryDirectory(prefix='aegis argv ') as temporary:
            base=Path(temporary)
            folder=base/'working directory with spaces'
            folder.mkdir()
            arguments=['','with spaces','a"quote','C:\\a folder\\','backslash\\"quote',"operator's destination",'Unicode-\u00e9']
            expected=base/'expected args.json'
            expected.write_text(json.dumps(arguments))
            child=base/'argv probe.py'
            child.write_text("import json,sys; from pathlib import Path\n"
                "assert json.loads(Path(sys.argv[1]).read_text())==sys.argv[2:],repr(sys.argv[2:])\n"
                "print('CWD:'+str(Path.cwd()))\nprint('ARGUMENTS-VERIFIED')\n")
            values=[ '-u','-B',str(child),str(expected),*arguments ]
            body='Set-Location -LiteralPath '+literal(folder)+"\n$null=Invoke-AegisNative "+literal(sys.executable)+\
                ' @('+','.join(literal(value) for value in values)+")\n"
            result=self.run_ps(base,body)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('ARGUMENTS-VERIFIED',result.stdout)
            self.assertIn('CWD:'+str(folder),result.stdout)

    def test_interactive_failure_stops_before_dependent_step(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=self.run_ps(Path(temporary),'$null=Invoke-AegisNative '+literal(sys.executable)+
                " @('-B','-c','raise SystemExit(11)')\nWrite-Output 'DEPENDENT-STEP-STARTED'\n")
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('DEPENDENT-STEP-STARTED',result.stdout)
            self.assertIn('exit 11',result.stdout+result.stderr)

    def test_native_python_single_quotes_survive_powershell_51(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_ps(Path(temporary), "$r=Invoke-AegisNative "+literal(sys.executable)+
                " @('-B','-c',\"print('quoted value')\") -Capture\n"
                "if($r.Text.Trim() -ne 'quoted value'){throw 'Python quoting changed'}\n")
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def scenario(self, *, install=True, database=False, overrides=None, options=None, missing=None, committed=False):
        temporary = tempfile.TemporaryDirectory(prefix='aegis setup ')
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        repo = base/'repository with spaces'
        deploy = repo/'ags_deploy'
        deploy.mkdir(parents=True)
        if not (options or {}).get('NoVenv'):
            (repo/'.venv/Scripts').mkdir(parents=True)
            (repo/'.venv/Scripts/python.exe').write_bytes(b'offline placeholder; never executed')
        (repo/'ags_backend').mkdir()
        (repo/'ags_backend/requirements-oracle.txt').write_text('oracledb==26.0.1\n')
        kubeconfig = base/'destination.yaml'
        kubeconfig.write_text('synthetic; local kubectl is stubbed')
        wallet = base/'wallet.zip'
        wallet.write_bytes(b'synthetic; Oracle is stubbed')
        values = {'DB_Object':'Y' if database else 'N','DeployFrontend':'N' if database else 'Y',
                  'DeployBackend':'N' if database else 'Y','SourcePath':'','Ref':'HEAD',
                  'Kubeconfig':str(kubeconfig),'Context':'offline','ValidationReference':'synthetic CI run',
                  'WalletPath':str(wallet),'DatabaseOwner':'APP','ServiceAlias':'test_low','ExpectedService':'test.service'}
        values.update(overrides or {})
        inputs = deploy/'aegis-oci-inputs.json'
        inputs.write_text(json.dumps(values))
        options_path = base/'options.json'
        options_path.write_text(json.dumps(options or {}))
        calls_path = base/'calls.jsonl'
        preamble = '$script:testOptions=Get-Content -LiteralPath '+literal(options_path)+' -Raw|ConvertFrom-Json\n'
        preamble += '$script:testCalls='+literal(calls_path)+"\n$script:testTools=@{git=$true;kubectl=$true;docker=$true;oci=$true;py=$true;winget=$true}\n"
        for name in missing or []:
            preamble += '$script:testTools['+literal(name)+"]=$false\n"
        if (options or {}).get('RelativeInputs'):
            preamble += 'Set-Location -LiteralPath '+literal(repo)+'\n'
        preamble += r'''
function Get-AegisApplication { param($Name) if($script:testTools.ContainsKey($Name) -and $script:testTools[$Name]) { return $Name }; return $null }
function Get-AegisFreeSpaceGB { param($Repository) if($script:testOptions.LowDisk){return 1};return 100 }
function Invoke-AegisNative {
    param([string]$Program,[string[]]$Arguments,[switch]$Capture,[switch]$AllowFailure)
    @{program=$Program;arguments=@($Arguments)}|ConvertTo-Json -Compress|Add-Content -LiteralPath $script:testCalls
    $code=0;$text=''
    if($Program -eq 'git') {
        if($Arguments -contains 'ls-files') { $code=1;if($script:testOptions.TrackedJson){$code=0} }
        elseif($Arguments -contains 'check-ignore') { if($script:testOptions.UnignoredJson){$code=1} }
        else { $text='a'*40 }
    }
    elseif($Program -eq 'winget') {
        if($script:testOptions.InstallFailure){$code=1}
        else {
            switch($Arguments[$Arguments.IndexOf('--id')+1]) {
                'Git.Git' {$script:testTools.git=$true}
                'Kubernetes.kubectl' {$script:testTools.kubectl=$true}
                'Docker.DockerDesktop' {$script:testTools.docker=$true}
                'Python.Python.3.12' {$script:testTools.py=$true}
            }
        }
    }
    elseif($Program -eq 'kubectl') {
        $text=@{contexts=@(@{name='offline';context=@{user='operator'}});users=@(@{name='operator';user=@{exec=@{command='oci';args=@('ce','cluster','generate-token')}}})}|ConvertTo-Json -Depth 8 -Compress
    }
    elseif($Program -eq 'docker') {
        if($Arguments[0] -eq 'info') { $text='linux';if($script:testOptions.WindowsEngine){$text='windows'} }
        if($Arguments[0] -eq 'buildx') {$text='Platforms: linux/amd64, linux/arm64';if($script:testOptions.WrongPlatform){$text='Platforms: linux/amd64'} }
        if($script:testOptions.RegistryFailure -and ($Arguments[0] -in @('login','manifest'))){$code=1}
    }
    elseif($Arguments -match 'setup-preflight.py$') {
        if($script:testOptions.TargetFailure){$code=1}
        else {
            $output=$Arguments[$Arguments.IndexOf('--output')+1]
            $components=@('frontend','backend');if($script:testOptions.DatabaseOnly){$components=@()}
            $result=@{state='preflight-only';registry='registry.invalid';registry_namespace='test';preflight=@{state='preflight-only';database_installed=$false;builds='Not run';publication='Not attempted';source_commit=('a'*40);source_mode=$(if($Arguments -contains '--working-tree'){'working-tree'}else{'committed'});components=$components;platform='linux/arm64';previous_images=@{'aegis-web'=@{web=('registry.invalid/test/ags-aegis-web@sha256:'+('b'*64))};'aegis-api-worker'=@{api=('registry.invalid/test/ags-aegis-backend@sha256:'+('c'*64))}}}}
            if($script:testOptions.BadPreflight){$result.state='stopped'}
            $result|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $output -Encoding UTF8
        }
    }
    elseif($Arguments -contains 'venv') {
        $location=$Arguments[-1]
        New-Item -ItemType Directory -Path (Join-Path $location 'Scripts') -Force|Out-Null
        Set-Content -LiteralPath (Join-Path $location 'Scripts\python.exe') -Value 'offline placeholder'
    }
    elseif($Arguments -contains 'pip') {
        if($Arguments -contains 'oci-cli') { $script:testTools.oci=$true }
        else { $script:testOptions.OracleMissing=$false }
    }
    elseif(($Arguments -join ' ') -match 'oracledb') { $text='26.0.1';if($script:testOptions.OracleMissing){$code=1} }
    elseif($Arguments -contains '-c') { $text='True' }
    if($code -ne 0 -and -not $AllowFailure){throw 'Simulated prerequisite command failure'}
    return [pscustomobject]@{ExitCode=$code;Text=$text}
}
'''
        selected_inputs = r'.\ags_deploy\aegis-oci-inputs.json' if (options or {}).get('RelativeInputs') else inputs
        body = preamble+'try { $result=Invoke-AegisPrerequisites -DeploymentRoot '+literal(deploy)+' -Inputs '+literal(selected_inputs)+\
            ' -InstallMissing:$'+str(install).lower()+' -CommittedSource:$'+str(committed).lower()+"; Write-Output ('COMPLETED:'+ $result.State) } catch { Write-Output ('BLOCKED:'+ $_.Exception.Message); exit 1 }\n"
        result = self.run_ps(base, body)
        reports = list((repo/'ags_runtime/deployment-setup').glob('*/result.json'))
        self.assertEqual(len(reports), 1, result.stdout+result.stderr)
        report = json.loads(reports[0].read_text(encoding='utf-8-sig'))
        calls = [json.loads(line) for line in calls_path.read_text(encoding='utf-8-sig').splitlines()] if calls_path.exists() else []
        forbidden = [c for c in calls if c['program']=='docker' and c['arguments'][0] in ('build','push')]
        forbidden += [c for c in calls if c['program']=='kubectl' and any(a in c['arguments'] for a in ('apply','set','patch','scale'))]
        self.assertEqual(forbidden, [], 'Setup must never build/publish/update workloads')
        return result,report,calls

    def test_setup_default_uses_local_head_and_committed_option_uses_json_ref(self):
        for committed in (False,True):
            with self.subTest(committed=committed):
                result,report,calls=self.scenario(committed=committed,overrides={'Ref':'pinned-source'})
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(report['SourceMode'],'committed' if committed else 'working-tree')
                resolves=[c for c in calls if c['program']=='git' and 'rev-parse' in c['arguments']]
                self.assertEqual(resolves[0]['arguments'][-1],'pinned-source^{commit}' if committed else 'HEAD^{commit}')
                checks=[c for c in calls if '--output' in c['arguments']]
                self.assertEqual('--working-tree' in checks[0]['arguments'],not committed)

    def test_healthy_setup_checks_selected_target_and_authenticates_registry(self):
        result,report,calls=self.scenario()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(report['State'],'ready')
        self.assertTrue(any(c['arguments'][0]=='login' for c in calls if c['program']=='docker'))

    def test_fresh_workstation_installs_tools_and_creates_python_environment(self):
        result,report,calls=self.scenario(options={'NoVenv':True},missing=['py','git','kubectl','docker','oci'])
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        packages={c['arguments'][c['arguments'].index('--id')+1] for c in calls if c['program']=='winget'}
        self.assertEqual(packages,{'Git.Git','Python.Python.3.12','Kubernetes.kubectl','Docker.DockerDesktop'})
        self.assertTrue(any('venv' in c['arguments'] for c in calls))
        self.assertTrue(any('oci-cli' in c['arguments'] for c in calls))

    def test_missing_oracle_driver_is_installed_only_when_setup_can_install(self):
        for install in (True,False):
            with self.subTest(install=install):
                result,report,calls=self.scenario(install=install,database=True,options={'OracleMissing':True,'DatabaseOnly':True})
                self.assertEqual(result.returncode==0,install,result.stdout+result.stderr)
                installs=[c for c in calls if 'pip' in c['arguments']]
                self.assertEqual(bool(installs),install)
                if install:
                    self.assertTrue(any(str(a).endswith('requirements-oracle.txt') for c in installs for a in c['arguments']))

    def test_relative_input_path_uses_powershell_location(self):
        result,report,calls=self.scenario(options={'RelativeInputs':True})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(Path(report['Inputs']).is_absolute())

    def test_read_only_mode_never_installs_starts_or_logs_in(self):
        result,report,calls=self.scenario(install=False)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(any(c['program']=='winget' for c in calls))
        self.assertFalse(any(c['arguments'][0] in ('login','desktop') for c in calls if c['program']=='docker'))

    def test_missing_git_is_installed_and_rechecked(self):
        result,report,calls=self.scenario(missing=['git'])
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(any('Git.Git' in c['arguments'] for c in calls))

    def test_read_only_missing_git_stops_before_install_or_target(self):
        result,report,calls=self.scenario(install=False,missing=['git'])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(report['State'],'blocked')
        self.assertFalse(any(c['program']=='winget' or '--output' in c['arguments'] for c in calls))

    def test_database_only_skips_docker_kubernetes_and_registry(self):
        result,report,calls=self.scenario(database=True,options={'DatabaseOnly':True},missing=['docker','kubectl','oci'])
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(any(c['program'] in ('docker','kubectl','oci') for c in calls))

    def test_invalid_private_fields_are_rejected_before_installation(self):
        result,report,calls=self.scenario(overrides={'Password':'DO-NOT-LOG-THIS'})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(calls,[])
        self.assertNotIn('DO-NOT-LOG-THIS',json.dumps(report)+result.stdout+result.stderr)

    def test_all_n_is_rejected_before_installation(self):
        result,report,calls=self.scenario(overrides={'DB_Object':'N','DeployFrontend':'N','DeployBackend':'N'})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(calls,[])

    def test_failed_target_check_cannot_claim_readiness_or_start_registry_login(self):
        result,report,calls=self.scenario(options={'TargetFailure':True})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(report['State'],'blocked')
        self.assertFalse(any(c['arguments'][0]=='login' for c in calls if c['program']=='docker'))

    def test_windows_engine_low_disk_and_wrong_platform_are_blocked(self):
        for option in ('WindowsEngine','LowDisk','WrongPlatform'):
            with self.subTest(option=option):
                result,report,calls=self.scenario(options={option:True})
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(report['State'],'blocked')

    def test_registry_failure_or_bad_preflight_is_not_ready(self):
        for option in ('RegistryFailure','BadPreflight','TrackedJson','UnignoredJson','InstallFailure'):
            with self.subTest(option=option):
                result,report,calls=self.scenario(options={option:True},missing=['git'] if option=='InstallFailure' else None)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(report['State'],'blocked')


if __name__=='__main__': unittest.main()
