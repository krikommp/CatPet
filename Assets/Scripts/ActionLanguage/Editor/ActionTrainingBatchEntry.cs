using System;

namespace PetLive2d.ActionLanguage.Editor
{
    /// <summary>Argument-only bridge for automation; recording remains in BatchVideoRecorder.</summary>
    public static class ActionTrainingBatchEntry
    {
        public static string Run(string queuePath, string donePath, string snapshotRoot)
        {
            if (!BatchVideoRecorder.RunBatch(queuePath, donePath, snapshotRoot, out string error))
                throw new InvalidOperationException(error);
            return BatchVideoRecorder.LastReportPath;
        }

        public static bool IsRunning() => BatchVideoRecorder.IsRunning;
    }
}
