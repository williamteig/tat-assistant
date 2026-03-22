# TAT Assistant

The central knowledge engine for **The Audition Technique** universe. Pulls content from Vimeo, Circle, and social media into a cloud database (Supabase), generates consolidated knowledge documents, and uploads them to a Claude project â€” keeping the AI assistant permanently up to date with Greg's teachings, community discussions, and social content.

---

## Architecture

```
[Vimeo]  [Circle]  [Instagram / Facebook / YouTube / TikTok]
     â†“        â†“                      â†“
         GitHub Actions (every 6 hours)
                  â†“
          Supabase PostgresQL
         (cloud database â€” source of truth)
                  â†“
         knowledge/*.md  (consolidated documents)
                  â†“
          Anthropic Files API â†’  TAT Claude Project
```

---

## Repository structure

```
 tat-assistant/
â”œâ”€â”€â¦ run_sync.py                        â† Orchestrator â€” runs everything
â”œâ”€â”€â¦ requirements.txt
â”‚
â”œâ”€â”€â¦ data/
â”‚  â””â”€â”€â¦ schema.sql                     â†Run once in Supabase SQL editor
â”‚  â””â”€â”€â¦ db.py                            â† Supabase client helper
â”‚
â”œâ”€â”€â¦ knowledge/                         â† Auto-generated, uploaded to Claude
â”‚   â”œâ”€â”€â¦ transcripts_core.md
¸¥ ˆ€ƒŠRsŠRŠRŠšÑÉ…¹ÍÉ¥ÁÑÍ}±¥Ù•ÍÑÉ•…µÌ¹µ+ŠR€ƒŠRsŠRŠRŠš½µµÕ¹¥Ñå}¥É±”¹µ*â”‚")IN)H)H*j6ö6–ÅöfVVBæÖ@®)H ®)IÎ)H)H)ªFööÇ2ğ®)H")IÎ)H)H*jf–ÖVòöfWF6…÷G&ç67&—G2ç’(iVÆÇ2G&ç67&—G2g&öÒf–ÖVğ®)H")IÎ)H)H*j6—&6ÆRöfWF6…÷÷7G2ç’(iVÆÇ2÷7G2g&öÒ6—&6ÆR6öÖ×Væ—G®)H")IÎ)H)H*j6ö6–ÂöÖöæ—F÷"ç’(iVÆÇ2÷7G2g&öÒÆÂ6ö6–ÂÆFf÷&×0®)H")IN)H)H*j6ÆVFRğ«ŠRˆ8¥'8¥ 8¥ 8©¨Ù[™\˜]WÚÛ›İÛYÙKœH8¡¤Z[ÈHÛ›İÛYÙH›Yš[\Â¸¥ ˆ8¥%8¥ 8¥ 8©¨\ØYÚÛ›İÛYÙKœH8¡¤\ØYÈ[HÈ[›ÜXÈš[\ÈTB¸¥ ‚¸¥%8¥ 8¥ 8¦¨™Ú]X‹İÛÜšÙ›İÜËÜŞ[˜Ë[[8¡¤Ú]XˆXİ[ÛœÈ8 %[œÈ]™\Hˆİ\œÂ˜‚‹KKB‚ˆÈÈš\œİ][YHÙ]\‚ˆÈÈÈKˆİ\X˜\ÙB‚ŒKˆÜ™X]HHœ™YH›Ú™Xİ]Üİ\X˜\ÙK˜ÛÛWJÎ‹ËÜİ\X˜\ÙK˜ÛÛJBŒ‹ˆÛÈÈ
Š”ÔSY]ÜŠŠˆ[™\İH
È[ˆHÛÛ[ÈÙˆ]KÜØÚ[XKœÜ[ŒËˆÛÜH[İ\ˆ
Š”›Ú™XİT“
Šˆ[™
ŠœÙ\šXÙWÜ›ÛHÙ^JŠˆ
›Ú™XİÙ][™ÜÈ8¡¤ˆTJB‚ˆÈÈÈ‹ˆ[š\›Û›Y[˜\šXX›\Â‚˜˜\Ú˜Ü™[‹™^[\H™[‚ˆÈš[[ˆ[˜[Y\È[ˆ™[‚˜‚ˆÈÈÈËˆ[œİ[\[™[˜ÚY\Â‚˜˜\Úœ\[œİ[\ˆ™\]Z\™[Y[Ë˜‚ˆÈÈÈˆš\œİŞ[˜È
ØØ[
B‚˜˜\ÚˆÈ[™]ÚÙˆ]™\][™È
š\œİ[ŠBœ]Ûˆ[—ÜŞ[˜ËœHKY[K\ÚÚ\]\ØY‚ˆÈ[ˆ\ØYÈÛ]YHÛ˜ÙH[İH]™HHS•“ÔP×ĞTWÒÑVHÙ]œ]ÛˆÛÛËØÛ]YKİ\ØYÚÛ›İÛYÙKœB˜‚ˆÈÈÈKˆÚ]XˆXİ[ÛœÈ
]]ÛX]Y
B‚Y[[İ\ˆTHÙ^\È\È
Š‘Ú]XˆÙXÜ™]ÊŠˆ
Ù][™Üø¡¤ˆÙXÜ™]È[™˜\šXX›\È8¡¤ˆXİ[ÛœÊN‚‚ŸÙXÜ™]\ØÜš\[ÛˆŸKK_KK_ŸÕTPTÑWÕT“[İ\ˆİ\X˜\ÙH›Ú™XİT“ŸÕTPTÑWÔÑT•’PÑWÒÑVXİ\X˜\ÙHÙ\šXÙH›ÛHÙ^HŸS•“ÔP×ĞTWÒÑVX[›ÜXÈTHÙ^HŸ’SQS×ĞPĞÑTÔ×ÕÒÑS˜š[Y[È\œÛÛ˜[XØÙ\ÜÈÚÙ[ˆŸÒTÓWĞTWÕÒÑS˜Ú\˜ÛHTHÚÙ[ˆŸÒTÓWĞÓÓSUS’UWÔÓQØ[İ\ˆÚ\˜ÛHİX™ÛXZ[ˆŸNS”ÕQÔSWĞPĞÓÕS•ÒQ[œİYÜ˜[H\Ú[™\ÜÈXØÛİ[QŸNS”ÕQÔSWĞPĞÑTÔ×ÕÒÑS˜Û™Ë[]™Y[œİYÜ˜[HÚÙ[ˆŸPÑP“ÓÒ×ÔQÑWÒQ˜XÙX›ÛÚÈYÙHQŸPÑP“ÓÒ×ĞPĞÑTÔ×ÕÒÑS˜˜XÙX›ÛÚÈYÙHXØÙ\ÜÈÚÙ[ˆŸSÕUP‘WĞTWÒÑVXÛÛÙÛHÛİYTHÙ^HŸSÕUP‘WĞÒS“‘SÒQU[İUX™HÚ[›™[Q‚•HÛÜšÙ›İÈ[œÈ]™\Hˆİ\œÈ]]ÛX]XØ[H[™ÛÛ[Z]È[H\]YÛ›İÛYÙHØÜË‚‚‹KKB‚ˆÈÈ[›š[™È[™]šYX[İ\Â‚˜˜\Úœ]ÛˆÛÛËİš[Y[ËÙ™]Úİ˜[œØÜš\ËœHK[™]Ë[Û›HÈÛ›H™]Èš[Y[È\ØYÂœ]ÛˆÛÛËØÚ\˜ÛKÙ™]ÚÜÜİËœHÈ™]ÈÚ\˜ÛHÜİÂœ]ÛˆÛÛËÜÛØÚX[Û[Ûš]Ü‹œHK\]›Ü›H[œİYÜ˜[HÈÛ™H]›Ü›Bœ]ÛˆÛÛËØÛ]YKÙÙ[™\˜]WÚÛ›İÛYÙKœHÈ™XZ[ØÜÂœ]ÛˆÛÛËØÛ]YKİ\ØYÚÛ›İÛYÙKœHÈ\ÚÈÛ]YB˜‚‹KKB‚ˆÈÈY[™ÈÛ›İÛYÙHÈ[İ\ˆÛ]YH›Ú™Xİ‚Y\ˆ[›š[™È\ØYÚÛ›İÛYÙKœXHØÜš\š[ÈH[›ÜXÈš[HQË‚•ÈY[HÈHUÛ]YH›Ú™Xİ‚‚ŒKˆÜ[ˆØÛ]YK˜ZWJÎ‹ËØÛ]YK˜ZJH8¡¤ˆU\ÜÚ\İ[›Ú™XİŒ‹ˆ
Š”›Ú™XİÙ][™ÜÈ8¡¤ˆÛ›İÛYÙH8¡¤ˆYÛÛ[
Š‚ŒËˆ\ØYHš[\Èœ›ÛHHÛ›İÛYÙKØ›Û\ˆ\™XİB‚•HÚ]XˆXİ[ÛœÈ›İ]]ÛX]XØ[H™KYÙ[™\˜]\È[™™K]\ØYÈ\ÙHš[\È]™\Hˆİ\œËÛÈ[İ\ˆÛ]YH›Ú™Xİİ^\Èİ\œ™[Ú]İ][HX[X[ÛÜšË‚