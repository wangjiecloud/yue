import { Asset } from 'expo-asset';

import demoPackModule from '../../assets/demo/course.yuepack';
import { importPack, type ImportResult } from './pack';
import { PackError } from './util';

export async function ensureDemoCourse(): Promise<ImportResult> {
  const asset = Asset.fromModule(demoPackModule);
  const downloaded = await asset.downloadAsync();
  if (!downloaded.localUri) {
    throw new PackError('内置演示课程无法解包');
  }
  return importPack(downloaded.localUri, true);
}
