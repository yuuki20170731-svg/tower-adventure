using UnityEditor;

public class AdventureArtImport : AssetPostprocessor
{
    public override uint GetVersion() { return 1; }
    void OnPreprocessTexture()
    {
        if (!assetPath.EndsWith("_hd.png")) return;
        var importer = (TextureImporter)assetImporter;
        importer.textureType = TextureImporterType.Default;
        importer.npotScale = TextureImporterNPOTScale.None;
        importer.alphaIsTransparency = true;
        importer.mipmapEnabled = false;
        importer.maxTextureSize = 4096;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.filterMode = UnityEngine.FilterMode.Bilinear;
    }
}
