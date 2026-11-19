import {uploadId} from './private-upload-transport';
import type {UploadJournal} from './private-upload-draft';
export const UPLOAD_JOURNAL_KEY='slc.private-upload.attempt.v1';
/** Deliberately retains the marker after success. No UI reset can bypass unknown writes. */
export function browserUploadJournal(storage:Pick<Storage,'getItem'|'setItem'>,locks:Pick<LockManager,'request'>|undefined):UploadJournal {
 const read=()=>{const raw=storage.getItem(UPLOAD_JOURNAL_KEY);if(raw===null)return null;if(raw.length>128)throw Error('invalid journal');const v=JSON.parse(raw);if(!v||Object.keys(v).sort().join(',')!=='request_id,version'||v.version!==1||!uploadId(v.request_id))throw Error('invalid journal');return v.request_id as string;};
 return {read,async claim(id){if(!uploadId(id)||!locks)throw Error('journal unavailable');return locks.request(UPLOAD_JOURNAL_KEY,{mode:'exclusive'},async()=>{if(read())return false;storage.setItem(UPLOAD_JOURNAL_KEY,JSON.stringify({version:1,request_id:id}));if(read()!==id)throw Error('journal unavailable');return true;});}};
}
