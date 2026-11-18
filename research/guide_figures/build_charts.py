import json,glob
import matplotlib.pyplot as plt
import numpy as np
D={m:[] for m in ['qwen2.5-3b','qwen3-4b','gemma3-4b']}
for p in glob.glob('drive-download-*/*.jsonl'):
 for line in open(p,encoding='utf8'):
  r=json.loads(line);D[r['model']].append(r)
models=list(D); names=['Qwen2.5-3B','Qwen3-4B','Gemma-3-4B']; variants=['c2_var1','c3_var2','c4_var3','c5_var4']; conds=['c0_native','c1_modal','variant_mean','c6_typo','c7_norm']; labels=['Native','Modal Roman','Rule variants','Typos','Back-translit.']; colors=['#287A60','#3A6FA5','#C9822B','#A94F54','#7857A5']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':10,'legend.fontsize':8,'figure.dpi':220})
fig,ax=plt.subplots(figsize=(7.0,3.3));x=np.arange(len(conds));w=.23
for j,m in enumerate(models):
 vals=[]
 for c in conds:
  if c=='variant_mean': val=np.mean([sum(r[v]==r['gold'] for r in D[m])/len(D[m])*100 for v in variants])
  else:val=sum(r[c]==r['gold'] for r in D[m])/len(D[m])*100
  vals.append(val)
 ax.bar(x+(j-1)*w,vals,w,label=names[j],color=['#3D6C91','#D08B45','#6A8D73'][j])
ax.axhline(25,color='#777',ls='--',lw=1,label='25% chance');ax.set_ylabel('Accuracy (%)');ax.set_xticks(x,labels);ax.set_ylim(0,80);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False);ax.legend(ncol=4,frameon=False);fig.tight_layout();fig.savefig('guide_figures/accuracy_by_condition.png',bbox_inches='tight');plt.close(fig)
fig,ax=plt.subplots(figsize=(7.0,3.3));x=np.arange(3);w=.2
series=[]
for m in models:
 rs=D[m];N=len(rs); a=0;t=0;agree=0;pair=0
 for r in rs:
  v=[r['c1_modal']]+[r[z] for z in variants];a+=any(z!=v[0] for z in v[1:]);t+=r['c6_typo']!=v[0];agree+=all(z==v[0] for z in v[1:]);pair+=sum(v[i]==v[j] for i in range(5) for j in range(i+1,5))
 series.append([a/N*100,t/N*100,agree/N*100,pair/(N*10)*100])
labels2=['Any of 4 variants flips','Single typo flips','All five agree','Pairwise agreement']
for j,(lab,color) in enumerate(zip(labels2,['#B9783E','#9A5964','#3E806D','#5B7D9B'])):ax.bar(x+(j-1.5)*w,[z[j] for z in series],w,label=lab,color=color)
ax.set_ylabel('Cases (%)');ax.set_xticks(x,names);ax.set_ylim(0,100);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False);ax.legend(ncol=2,frameon=False);fig.tight_layout();fig.savefig('guide_figures/answer_stability.png',bbox_inches='tight');plt.close(fig)
fig,axs=plt.subplots(1,3,figsize=(7,3.1),sharey=True);langs=['hi','bn','ta'];ln=['Hindi','Bengali','Tamil'];show=['c0_native','c1_modal','c7_norm'];labs=['Native','Modal Roman','Back-translit.'];
for ax,m,n in zip(axs,models,names):
 for k,c in enumerate(show):
  vals=[]
  for lang in langs:
   rs=[r for r in D[m] if r['lang']==lang];vals.append(sum(r[c]==r['gold'] for r in rs)/len(rs)*100)
  ax.bar(np.arange(3)+(k-1)*.23,vals,.23,label=labs[k],color=['#287A60','#3A6FA5','#7857A5'][k])
 ax.set_title(n);ax.set_xticks(np.arange(3),ln,rotation=18);ax.set_ylim(0,80);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
axs[0].set_ylabel('Accuracy (%)');axs[-1].legend(frameon=False,bbox_to_anchor=(1.02,1),loc='upper left');fig.tight_layout();fig.savefig('guide_figures/language_accuracy.png',bbox_inches='tight');plt.close(fig)
print('guide charts ready')
