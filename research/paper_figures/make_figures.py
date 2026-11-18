import json,glob,collections
import matplotlib.pyplot as plt
import numpy as np
D=collections.defaultdict(list)
for p in glob.glob('drive-download-*/*.jsonl'):
 for line in open(p,encoding='utf-8'):
  r=json.loads(line);D[r['model']].append(r)
models=['qwen2.5-3b','qwen3-4b','gemma3-4b'];names=['Qwen2.5-3B','Qwen3-4B','Gemma-3-4B'];langs=['hi','bn','ta'];langnames=['Hindi','Bengali','Tamil']
conds=['c0_native','c1_modal','variants','c6_typo','c7_norm'];labels=['Native','Modal Roman','Rule variants','Typos','Back-translit.']
colors=['#287A60','#3A6FA5','#C9822B','#A94F54','#7857A5']
acc={};flip={}
for m in models:
 rs=D[m];acc[m]=[]
 for c in conds:
  if c=='variants': v=np.mean([sum(r[x]==r['gold'] for r in rs)/len(rs)*100 for x in ['c2_var1','c3_var2','c4_var3','c5_var4']])
  else:v=sum(r[c]==r['gold'] for r in rs)/len(rs)*100
  acc[m].append(v)
 vals=[]
 for typ in ['variant','typo']:
  n=0
  for r in rs:
   if typ=='variant':n+=any(r[x]!=r['c1_modal'] for x in ['c2_var1','c3_var2','c4_var3','c5_var4'])
   else:n+=r['c6_typo']!=r['c1_modal']
  vals.append(n/len(rs)*100)
 flip[m]=vals
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.labelsize':8,'legend.fontsize':7,'figure.dpi':220})
# Fig 1: overall condition accuracy grouped by model
fig,ax=plt.subplots(figsize=(7.1,3.1));x=np.arange(5);w=.23
for i,m in enumerate(models):ax.bar(x+(i-1)*w,acc[m],w,label=names[i],color=['#3D6C91','#D08B45','#6A8D73'][i])
ax.axhline(25,color='#777',ls='--',lw=1,label='Four-choice chance');ax.set_ylim(0,80);ax.set_ylabel('Accuracy (%)');ax.set_xticks(x,labels);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False);ax.legend(ncol=4,frameon=False,loc='upper right');fig.tight_layout();fig.savefig('paper_figures/fig1_accuracy.png',bbox_inches='tight');plt.close(fig)
# Fig 2: change rates
fig,ax=plt.subplots(figsize=(7.1,3.1));x=np.arange(3);w=.32
for i,(title,k) in enumerate([('At least one of four variants',0),('One typo condition',1)]):
 ax.bar(x+(i-.5)*w,[flip[m][k] for m in models],w,label=title,color=['#B9783E','#637EA5'][i])
ax.set_ylim(0,75);ax.set_ylabel('Questions with changed answer (%)');ax.set_xticks(x,names);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False);ax.legend(frameon=False);fig.tight_layout();fig.savefig('paper_figures/fig2_flip_rates.png',bbox_inches='tight');plt.close(fig)
# Fig 3: Language-wise accuracy, 3 panels
fig,axs=plt.subplots(1,3,figsize=(7.1,2.8),sharey=True)
cc=['c0_native','c1_modal','variants','c6_typo','c7_norm']
for ax,m,name in zip(axs,models,names):
 x=np.arange(3);w=.15
 for i,c in enumerate(cc):
  vals=[]
  for l in langs:
   rs=[r for r in D[m] if r['lang']==l]
   if c=='variants':v=np.mean([sum(r[z]==r['gold'] for r in rs)/len(rs)*100 for z in ['c2_var1','c3_var2','c4_var3','c5_var4']])
   else:v=sum(r[c]==r['gold'] for r in rs)/len(rs)*100
   vals.append(v)
  ax.bar(x+(i-2)*w,vals,w,color=colors[i],label=labels[i])
 ax.set_title(name);ax.set_xticks(x,langnames,rotation=18);ax.grid(axis='y',alpha=.18);ax.spines[['top','right']].set_visible(False);ax.set_ylim(0,80)
axs[0].set_ylabel('Accuracy (%)');axs[-1].legend(frameon=False,bbox_to_anchor=(1.02,1),loc='upper left');fig.tight_layout();fig.savefig('paper_figures/fig3_language_accuracy.png',bbox_inches='tight');plt.close(fig)
# Fig 4: mean pairwise agreement & all five agree
all5=[];pair=[]
for m in models:
 rs=D[m];agree=0;matches=0
 for r in rs:
  v=[r['c1_modal']]+[r[x] for x in ['c2_var1','c3_var2','c4_var3','c5_var4']]
  agree+=all(z==v[0] for z in v[1:]);matches+=sum(v[i]==v[j] for i in range(5) for j in range(i+1,5))
 all5.append(agree/len(rs)*100);pair.append(matches/(10*len(rs))*100)
fig,ax=plt.subplots(figsize=(7.1,3));x=np.arange(3);w=.32
ax.bar(x-w/2,all5,w,label='All five agree',color='#BA7941');ax.bar(x+w/2,pair,w,label='Pairwise agreement',color='#5B7D9B');ax.set_ylim(0,100);ax.set_ylabel('Agreement (%)');ax.set_xticks(x,names);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False);ax.legend(frameon=False);fig.tight_layout();fig.savefig('paper_figures/fig4_agreement.png',bbox_inches='tight');plt.close(fig)
print('charts created')
