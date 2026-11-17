using System;
using System.IO;
using System.Security.Cryptography;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PetLive2d.ActionLanguage.Editor
{
    /// <summary>Real renderer regression check: another overlapping preview must not alter this camera.</summary>
    public static class PreviewIsolationCheck
    {
        [Serializable] private sealed class Report
        {
            public bool passed, separateScenes, cameraSceneBound, disposedScenes;
            public string beforeSha256, overlappingSha256, movedSha256, error, checkedAtUtc;
            public int previewScenesBefore, previewScenesAfter;
        }

        public static string Run(string reportPath)
        {
            if (EditorApplication.isPlaying || BatchVideoRecorder.IsRunning || File.Exists(reportPath))
                throw new InvalidOperationException("Requires stopped editor, no recording and a new report path.");
            CubismModel source = null;
            foreach (var model in UnityEngine.Object.FindObjectsOfType<CubismModel>())
                if ((model.hideFlags & HideFlags.DontSave) == 0 && !model.name.StartsWith("__"))
                { source = model; break; }
            if (source == null) throw new InvalidOperationException("Missing source model.");
            var report = new Report { previewScenesBefore = EditorSceneManager.previewSceneCount,
                checkedAtUtc = DateTime.UtcNow.ToString("o") };
            var first = new PreviewSession(); var second = new PreviewSession();
            try
            {
                first.Initialize(source, null); first.Tick();
                report.beforeSha256 = Hash(first.PreviewTexture);
                second.Initialize(source, null); second.Tick(); first.Tick();
                report.overlappingSha256 = Hash(first.PreviewTexture);
                second.PreviewRoot.transform.GetChild(0).localPosition = new Vector3(0.18f, 0.12f, 0f);
                second.Tick(); first.Tick();
                report.movedSha256 = Hash(first.PreviewTexture);
                report.separateScenes = first.PreviewRoot.scene != second.PreviewRoot.scene;
                report.cameraSceneBound = first.PreviewRoot.GetComponentInChildren<Camera>().scene == first.PreviewRoot.scene;
                report.passed = report.separateScenes && report.cameraSceneBound &&
                    report.beforeSha256 == report.overlappingSha256 && report.beforeSha256 == report.movedSha256;
            }
            catch (Exception error) { report.error = error.ToString(); report.passed = false; }
            finally
            {
                first.Dispose(); second.Dispose();
                report.previewScenesAfter = EditorSceneManager.previewSceneCount;
                report.disposedScenes = report.previewScenesBefore == report.previewScenesAfter;
                report.passed &= report.disposedScenes;
                File.WriteAllText(reportPath, JsonUtility.ToJson(report, true));
            }
            if (!report.passed) throw new InvalidOperationException("Preview isolation check failed; see " + reportPath);
            return reportPath;
        }

        private static string Hash(RenderTexture texture)
        {
            var previous = RenderTexture.active;
            var pixels = new Texture2D(texture.width, texture.height, TextureFormat.RGBA32, false);
            try
            {
                RenderTexture.active = texture;
                pixels.ReadPixels(new Rect(0, 0, texture.width, texture.height), 0, 0);
                pixels.Apply();
                using (var hash = SHA256.Create())
                    return BitConverter.ToString(hash.ComputeHash(pixels.GetRawTextureData())).Replace("-", "").ToLowerInvariant();
            }
            finally { RenderTexture.active = previous; UnityEngine.Object.DestroyImmediate(pixels); }
        }
    }
}
