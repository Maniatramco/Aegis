# Aegis stop and start through the OCI portal

Use the OCI Console to stop the existing Aegis worker VM at the end of the day and start the same VM the next day. This stops WebUI, FastAPI and the worker together because they run on one node. Your existing database, bucket, vectors and persistent volumes are retained.

## Identify the correct VM

1. Sign in at https://cloud.oracle.com/.
2. Select **India West Mumbai**, region **ap-mumbai-1**, at the top of the Console.
3. Open **Navigation menu → Compute → Instances**. Select the compartment containing Aegis.
4. Open the instance with public IP **140.245.28.141**, private IP **10.42.1.30** and shape **VM.Standard.A1.Flex**, **2 OCPUs / 12 GB**.
5. Verify its OCID matches this existing Aegis node:

```text
ocid1.instance.oc1.ap-mumbai-1.anrg6ljrcbffg3icsmk34krt672mzuhgj4gdla6tkubac5c2k3oyvqxiyl2a
```

If you cannot find the instance, locate **Kubernetes Clusters OKE → ags-aegis-basic → Node pools → ags-aegis-a1-node-pool** and open the existing node's associated Compute instance. Do not select the load balancer IP **92.4.67.183** as the worker VM.

## Stop at the end of the day

1. Ask other users to finish their work and stop submitting new requests.
2. In Aegis, open **Manage workspace → Jobs & activity**. Wait until there are no queued or running uploads, indexing, extractions or re-extractions. Let any active chat answer finish too.
3. In the OCI portal, open the verified Compute instance above.
4. Open **Actions** or the three-dot menu and choose **Stop**.
5. Leave **Force stop the instance by immediately powering off** unchecked. Confirm **Stop instance**.
6. Wait until the instance status is **Stopped**. A graceful stop can take several minutes.
7. You can now close Docker Desktop or shut down your laptop.

The Aegis website becomes unavailable. The cluster can remain Active, and its worker can show NotReady while the VM is stopped; neither means the application is still serving requests. This portal procedure leaves the application replica settings intact for restart. [Oracle instructions for stopping an instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/restartinginstance-stop-instance.htm).

Use **Stop**, rather than **Terminate**, **Delete**, a node-pool resize to zero, or a cluster upgrade. Those are different operations and are not part of this daily procedure.

## Start the next day

1. Start your laptop and open Docker Desktop. Start the existing **aegis-oracle-ollama-1** container from Docker Desktop's Containers list if it is stopped.
2. In the OCI portal, open the same Compute instance.
3. Choose **Actions → Start** and wait for **Running**. [Oracle instructions for starting an instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/restartinginstance-start-instance.htm).
4. Allow several more minutes for Kubernetes and Aegis to recover. Running describes the VM; it does not by itself confirm the application is ready.
5. Restore the laptop model tunnel as described below if its launcher is no longer running.
6. Open https://aegis.92.4.67.183.sslip.io/ and sign in. Keep the laptop, Docker and tunnel online while using AI features.

If you previously used the PowerShell instructions to set application replicas to zero, starting the VM alone will leave those replicas at zero. Run the **Start the next day** block in [the PowerShell guide](AEGIS_DAILY_STOP_START.md) once to restore them. For subsequent portal-only daily stops, use this guide consistently; do not combine both stop procedures.

## Restore the laptop model connection

The OCI portal starts the cloud VM; it cannot start a tunnel process on your laptop. If the existing tunnel launcher remained running, it retries and reconnects automatically after the node becomes ready.

After a laptop restart, open this folder in Windows File Explorer:

```text
C:\Users\Laya\Documents\Codex\2026-10-09\new-chat\Aegis\local\ags_scripts
```

Right-click **start-oke-model-relay.ps1 → Run with PowerShell**. On Windows 11, the option may be under **Show more options**. Keep that PowerShell window open while using Aegis. Start only one tunnel launcher. It uses the existing SSH key and reconnects automatically; initial timeouts while the VM is starting can recover.

If you used the earlier PowerShell stop procedure, its `stop-model-relay` flag blocks this launcher. Use the existing PowerShell guide's start block to clear the pause and resume the connection correctly.

## Credit usage while stopped

Stopping this Standard Compute VM through the portal pauses its Compute billing. Disks, bucket, registry, database and load balancer remain allocated; their allowances and service pricing still apply. This is not a guarantee of zero total overnight cost. [Oracle billing for stopped instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm), [Oracle service pricing](https://www.oracle.com/cloud/price-list/).

Your existing documents, extraction results and vectors are not deleted by Stop or Start. No upgrade or new resource is required by these steps.

Prepared 14 October 2026 from the recorded Aegis resource IDs and Oracle's Console instructions. The VM was not stopped as a test; the application remains running for you.
