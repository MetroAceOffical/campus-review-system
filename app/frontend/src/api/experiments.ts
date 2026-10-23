import { ref,shallowRef } from 'vue'
import { request } from './http'
export interface ExperimentManifest {
  id:string;title:string;contentVersion:string;taskType:string;dataset:string;datasetRevision:string;frozenAt:string;updatedAt:string
  testSets:{id:string;label:string}[];models:{id:string;label:string;device:string;threshold:number;scoreType:string;hasHistory:boolean;selectedConfig:Record<string,unknown>}[]
  metricDefinitions:Record<string,string>;notes:string[];chartCapabilities:string[];splitProtocol:Record<string,unknown>;sourceFiles:{path:string;sha256:string;bytes:number}[]
}
export interface MetricValues { n:number;accuracy:number;macro_f1:number;positive_precision:number;positive_recall:number;positive_f1:number;macro_precision:number;macro_recall:number;roc_auc:number;confusion_matrix:number[][];end_to_end_ms_per_pair:number;errors:{false_positive:number;false_negative:number} }
export interface SearchRow {family:string;index:number;config:Record<string,unknown>;validation_macro_f1:number;fit_or_train_seconds:number;best_epoch:number|null;epochs_run:number|null;peak_allocated_bytes:number|null;peak_working_set_bytes:number|null;selected:boolean}
export interface HistoryRun { family:string;index:number;selected:boolean;bestEpoch:number;config:Record<string,unknown>;epochs:{epoch:number;mean_train_loss:number;validation_forward_seconds:number;single_predicted_class:boolean;validation_metrics:{macro_f1:number;accuracy:number;confusion_matrix_0_1:number[][]}}[] }
export interface ModelCurves {scoreType:string;roc:{fpr:number[];tpr:number[];thresholds:(number|null)[]};pr:{precision:number[];recall:number[];thresholds:number[];averagePrecision:number};histogram:{edges:number[];negative:number[];positive:number[]}}
export interface ExperimentBundle {manifest:ExperimentManifest;lastCheckedAt:string;warning?:string;metrics:{sets:Record<string,{n:number;models:Record<string,MetricValues>}>;splitCounts:Record<string,{n:number;labels:Record<string,number>}>};curves:{sets:Record<string,{models:Record<string,ModelCurves>}>};history:{split:string;runs:HistoryRun[]};search:{selectionMetric:string;configurations:SearchRow[];preprocessingComparisons:{policy:string;validation_metrics:{macro_f1:number}}[]}}
export const listExperiments=()=>request<{experiments:ExperimentManifest[];lastCheckedAt:string;warning?:string}>('/api/experiments')
export function createExperimentState(fetcher:(id:string)=>Promise<ExperimentBundle>=(id)=>request(`/api/experiments/${encodeURIComponent(id)}/bundle`)){
  const bundle=shallowRef<ExperimentBundle>(),checkedAt=ref(''),error=ref(''),loading=ref(false);let generation=0
  async function refresh(id:string){const current=++generation;loading.value=true
    try{const next=await fetcher(id);if(current!==generation)return
      if(!next.manifest?.id||!next.manifest.contentVersion)throw new Error('实验包结构无效')
      if(bundle.value?.manifest.contentVersion!==next.manifest.contentVersion||bundle.value.manifest.id!==next.manifest.id)bundle.value=next
      checkedAt.value=next.lastCheckedAt;error.value=next.warning??''
    }catch(failure){if(current===generation)error.value=failure instanceof Error?failure.message:'实验刷新失败'}finally{if(current===generation)loading.value=false}
  }
  function cancel(){generation++;loading.value=false}
  return {bundle,checkedAt,error,loading,refresh,cancel}
}
