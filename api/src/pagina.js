/**
 * A pagina de consulta, servida pelo proprio Worker na raiz.
 *
 * Porque nao a do basedados/site/: essa descarrega o huorm.db inteiro, 6 MB,
 * e corre SQL no browser com o sql.js. Funciona, mas obriga a alojar o
 * ficheiro noutro sitio e a esperar pelo descarregamento antes da primeira
 * pergunta. Esta pergunta aos endpoints que ja existem ao lado, por isso
 * responde de imediato e vive no mesmo endereco.
 *
 * As duas nao se anulam: a do sql.js aceita SQL livre, esta so as perguntas
 * que a API expoe. Quem quiser SQL arbitrario descarrega a base.
 */

export const PAGINA = `<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HUORM: informação farmacogenómica dos RCM portugueses</title>
<style>
  :root { --tinta:#1a1a1a; --suave:#666; --linha:#e0e0e0; --fundo:#fafafa; }
  * { box-sizing:border-box; }
  body { font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         color:var(--tinta); margin:0; background:#fff; }
  .caixa { max-width:1060px; margin:0 auto; padding:32px 20px 64px; }
  h1 { font-size:25px; margin:0 0 6px; font-weight:600; letter-spacing:-.01em; }
  .logo { height:62px; width:auto; display:block; margin:0 0 10px -4px; }
  .sub { color:var(--suave); margin:0 0 22px; max-width:62ch; }
  .estado { padding:10px 14px; background:var(--fundo); border:1px solid var(--linha);
            border-radius:6px; color:var(--suave); margin-bottom:26px; font-size:14px; }
  .estado.erro { background:#fff4f4; border-color:#f0c0c0; color:#a33; }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:.07em;
       color:var(--suave); margin:26px 0 10px; font-weight:600; }
  .perguntas { display:grid; gap:6px; }
  button { text-align:left; background:#fff; color:var(--tinta);
           border:1px solid var(--linha); border-radius:6px;
           padding:10px 13px; font-size:14px; cursor:pointer; font-family:inherit; }
  button:hover { border-color:var(--tinta); }
  button small { color:var(--suave); }
  .procura { display:flex; gap:8px; margin-top:6px; }
  .procura input { flex:1; padding:10px 12px; border:1px solid var(--linha);
                   border-radius:6px; font:inherit; }
  .procura button { flex:0 0 auto; background:var(--tinta); color:#fff;
                    border-color:var(--tinta); }
  table { border-collapse:collapse; width:100%; margin-top:18px; font-size:13px; }
  th,td { border-bottom:1px solid var(--linha); padding:7px 10px; text-align:left;
          vertical-align:top; }
  th { background:var(--fundo); font-weight:600; position:sticky; top:0; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  .rolo { max-height:560px; overflow:auto; border:1px solid var(--linha);
          border-radius:6px; margin-top:18px; }
  .rolo table { margin:0; }
  .contagem { margin-top:12px; color:var(--suave); font-size:13px; }
  tr.abre { cursor:pointer; }
  tr.abre:hover td { background:var(--fundo); }
  tr.abre td:first-child { font-weight:600; }
  .bloco h3 { font-size:13px; text-transform:uppercase; letter-spacing:.06em;
              color:var(--suave); margin:22px 0 0; font-weight:600; }
  .voltar { margin-top:16px; background:#fff; border:1px solid var(--linha);
            padding:7px 12px; font-size:13px; border-radius:6px; }
  .url { font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
         color:var(--suave); word-break:break-all; margin-top:10px; }
  footer { margin-top:52px; padding-top:20px; border-top:1px solid var(--linha);
           color:var(--suave); font-size:13px; }
  a { color:var(--tinta); }
</style>
</head>
<body>
<div class="caixa">

  <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAqgAAAFUCAMAAADf3j6RAAAAwFBMVEXacmAdHy/d1tWhW1MRGyzwtqJkT1T7xrGbm6JUMjdweYjbjHR5g48qNEihQz1XO0IKCXS4vMI7RVeXPTlcKitgXV28wca0gnb/AACqXl4ZHjBYLlj/dHQCDx7///9VVRVyQD+RPkKqVQCEe4L/AP+qqlWqqqqqqv///wAAAAAGFiz0lnbviGnVZ1n3o4fqemLpdl0BCRn7+vr1nYEADSIGFSsAAFUIFisHFSoJFivFW00GFSkGFCm3VUoAATr5s5mBFGL6AAAAQHRSTlP9/fr9E/39/fz9/f39/f39A/v8/QkE+v0BA1IHArABBP39A/4BAwMDAQD9/f39/f39/f39/I0DTnEx/a/R/QX9db/9SQAANWRJREFUeNrtnQdj4sqSqNUIBDKDPemEG/bu7tt9wcoaSSbD//9X21XdLbVyADzjd6ruuR6PB8sYfVTqCsYrCckHEINeAhIClYSEQCUhUElICFQSEgKVhEAlISFQSUgIVBIClYSEQCUhIVBJCFQSEgKVhEAlISFQSUgIVBIClYSEQCUhIVBJCFQSEgKVhIRAJSFQSUgIVBIClYSEQCUhIVBJCFQSEgKVhIRAJSFQSUgIVBISApWEQCUhIVBJSAhUEgKVhIRAJSFQSUgIVBISApWEQCUhIVBJSAhUEgKVhIRAJSEhUEkIVBISApWEQCUhIVBJSAhUEgKVhIRAJSEhUEkIVBISApWEhEAlIVB/pryB0I0kUElICNQb5G9zLtvtdgfC/9zv57/R/SRQfyWZ77fZ8XRyKnI6HbPtfk43lUD9+fJ9v+OMCjBTLo76tMD1uCNYCdSfq0m3ma5GNTqdFP+TH5xTtiVWCdSfTakOaJPgv592e7q7BOp7yz8EpRqhsRD8CouVlDg+bv+bbjCB+p7KdKdTmiKRzLLMFZcFCv/EtKwNcxSt4uHHLd1hAvXdMU0Fpc6LZS4Wy9lstuQiQOWfwN8Xiz8s2xGsplKr0j0mUN8lzN+dcgXJAdxYK6ASAEVIr9eFLvi1lcWUWgVUyVclUB8v21PhlDovJurOZQHl9QqkLuWXrwEI/8p1bTkFqzu6zQTqY2V/LDBl5mIp2QwKSZKEfwS7j67ANUgkrInJ4jyqolwVgfpI5zQrMH35YyFUZuK6ElDBKH6YKeGPkQDz/3NUZbrqRJ4qgfp4qx871gKVpQuSa9IkhzUoOIUPStteAVUm3Fsy/wTqY+Q3pU7jlGO6QFXqJjWR6nOmyyJ3DK6JBa4qkJqR+SdQH+GdqlOomP2xuAogAUwBa6FR5VeDxbIANVepAde/yv6To0qgPsLs51bfdDluOado/TmeSVBWrPiQ63JZBhUeHSS2OK8iUgnUu8tOxVD2eg0MlpFMylE/fFEQDLQuMEmV8D8Dwff1asrTrH8jUgnUR0T7KVenbqNnmhSU4h/Fo8Rnrgt5VZHGWqxWlqwEIFIJ1HtyKpOnse25biOpQa5Tqy5ArneXgtRrYH3dbDayaoWsP4F69zCKB/tuLg1xftn21xUugMr/sDZfra9fv24ccfx/lN0q1A1IoN6qTyWnzFy7bhOqQcnsB1Vdmz/kyp3UwNygRt18/cpEAWBGt5xAvac+dQzXrYEaaBwmHVLEWtZmY1mmaXGtyvUpVv4d/+2Y7ai1ikC9mdMU9Ona9RpI1VxStxnRMqfB2jLXmKfisKo+K1ECcDruiFUC9Ua7b1colaSK89OaM6B9XgU1kOeu/BvXdq2DJdsTAATqLZxGbgOorruWxVJJmdRKWiAIGkg17Lip04rqqgnU8fKvo+K0QaGCUjQsHhIxy5RaVVHaDSqiaqn2Km7781YrOlklUCdJ1sVpEnClCIhxsQKNU127yqq/qqxFHtUBQNlm89XaOGnOrUNKlUAdJVvJqdFk+AP3BeugBF7rIEdUnJ7qPqpMChQlVGsnFk2rjmU9QUPgbPZl9fQVegBi6MGiEkACdUzAL/OnRpNCDVwW41wUAVw5yGpItBbpVjdYay0Cq0/4P6xdWVmqW4VIJVAHy/eTyJ/6YVPE77IUM0vQN2WWjwKqSYCyQnWTtehHjS1sq3p6+sRFkDpbfSVSCdRpDurZ85I6hR5wykm1Tc8tElQVUINyLCU/5aoY3FG2+vEDO1WeANWVKl19Srn5dxiRSqCOM/x2GCUNoGJJKfcKErcxH4D6NGiOpETl1Gb2A4STugJQn3JSV05MOpVAHSwigxqzKPLq+jIwMWS33BZJOkA1U6hFZYJTQHXxqaRSZyvZAUBZKgJ1gOwgno9jkyvUBsPObTPnNEiaNClymoNay/aLutacU07qCjhdfSlIldMqPxMMBGqv4eeYpiw2vci7NihUGOfzEjT5BILUxM0rqcqYcsMPinr144dO6ieRohLyuyKVjD+BOiSS4gqVhWHYFCnZQHEiQBUkulBpstYD/kqVqsr0i3j/R0lmJVBnX2ZPMY/VnBMZfwK1X6FC6unsRe41qIdJPG5nMojyDKjZs16gdm/triucJvVIChzfWRnUH6sqqV9jSGGRSiVQu+W3I5b22V4UBlVQAT7TYYbrJcHatJk6RRWTJ7FF1dV6qKoKNU4rhr9BpeZuKqlUArVT8OyUOX7IPdRrUj/kDxBFnHuWlsahw2lTIptNG2z/1YKj05pCBS9Vz1BxQVeWVCqB2i1HWYPKPdQGUAWtHNO0GNfv6LPTGnxTKYxr3fjTj5osPkGOqqZST7T+h0Dt8lAFc34YcoV6bcLU80yZl88nSqdqsnQav6xbSP0jZg0eqkhRPX16KjJUv0uVuiceCNTOkB/PpEIeSl2DRk5twWcaO1+fRAp0Jaf1grvqmEFjEtWMGYs3PxpBrdj+Fdl+ArVHZFm/H0VR0AKqLQdIbFazEm5fOappzIE1r5VQCj+1AVSrAdQfeOKvgzrbYOMf8UCgdodSqR3B6Wmz5bdxfn/srGpW/IsVY29pbC01TSoTAQlkR0XMDyp0NavYfs1JVbaf4n4CtU3+POL+nTMHtdnyB7Ys05s16cYVE3vQzKXeeQJnVbIOdZY/aPOp1fb/Lm0/FfsTqJ2hVMwiI4qSJlADC8+N0tWPZlm8IGLC+tdBhViKx/SMi+N8LWpTqgmqFR2jEqidshMKMTSMqLHSFCqneIjfxiknFUjmjzD0OX9g+k0oueKgrpwNQ9k4m5mWSn160kD9HYuoaI4Kgdoiv4nOU98wDK8JVMOpl5VUQnjUuUycsiY4y0esowDEY/bjx4YJUPVjfwGqrlI3MUVTBGqf5bcjDmqji4oOahenHLorRkKpqAMMggVUA1imdxagrhyhTtlmNXtSV5pB3F8CFbtSTv+HiCBQ2y1/bHIX1Ujqx1KQCk2d5hRTIcvFRvamgqtgi5PWWGxIZT8sASpzvvCHWqwZ1N8lqHQ2RaA2yxHPRCGJGjUUpECGKW08XCqp1MVC6OVEpFy1HdPxZraRp63on85UULasgopamaqnCdRmwWw/dKA0gsoVaq/hx3jqakLan8dTDAKrtAA13aygPUAD1VJh/5Me9n8hUAnUPheVQUtfZNRL/NwAUk/Nh6BcBxZ6duYmELSn1ktabEiHYkD+HpCgctOPGVWlniGTqoX9BCqB2uuiimy/4dWPpUSBfl2hzp7Anm+sL+oLgdC9auEPTERV09CVi8ocHkytOLTym1Zg+3+vmv7/S0QQqE2SiaETYPm9eswPzVJO3UNdbVS9nzqtmgULrlKFV8pMcY5qClRlDhXTU/jfSgNV65yC9FRK6SkCtddFrYPqQTt//FTl9CllG+l35v3614Xoi45jO3dwPSSVoykhxY/M+dQE6uwLgE4JfwK13UXFqRNh2AQqklbreEqZ8DlxhKQkdYGN0fzvzMtnVARMFq+KZL8Q5jw1grpyuFNLR6gEarNsRRY1DLEYtTRbmv9hYCK0AuosR4451idLRvHL5Ipn/qlRqhJwKpgCqFZR6ZeDCkUpjCZQEqjN8iZiKajtB1ADrUsqkYf1cS3Zb6l0k/A25VnTzIUMFVfOhVb2cB6AUr6CWIA2B1UrS/lCZX4Ean8sZSCo2ogUOaMHx0Y9tShUGWXNHMxezSTWTB+0slZEa5zmoM5KoH7BQsAjHUwRqI1yxFgqrIIq1SqCuqpFUgo/4Z5a+IhZECxg1oqjD1FLXvQ+QFVB9VQH9UveinIhIgjUlqA/hXR/yfS7ngeTJizWkEXdOEzXqDMOqiUyqQFUBcRGdRYQj+V1lbop0lPanFRq7iNQO0HFbOh/SFATnHyCcZSHSVDUh7+3WX4nhUTTjAkXYNEAqutBjWCq0lOyfHpWRP1yCsXvv6/wR1EWlUDtyk6ZXgSmH432GmfuW448A5WtJNXclJJPsxloWDhruiYBg16+8jBqiwdYgtQ89lcHshqoX0TpFMX8BGoPqGEOqhtcF5ZTHNizTlDTIvoP4Lifw7guebqG0MoFpkIN52f9yvSj9qaDfgK1RbZyGnroeR6M7uf/GflEFDxnYvGXDlDlA59yUOMKqK7wPfVcqho9vQBQP33Jk/2URCVQu0DlcAlQPRg1bRTlpPBJWgumGkGFaCoA0+/UQHWLQAr1qsp2SVC5Sv3yZbXBRRaUmyJQ22SHevMMlp+Dek1Qm6bi/5a5aehCaQN1liQJQM8q035l0h+LW9hmkydRF4vFJ1yP8vuXL19TmuVHoPaBCkV+eNQfhSZLi8ln0KBnpbUpvCunBiqm8GdJsBYJ/6TWbS22nqEoTq+LJYLKo6kvcoUPGX4CtRNUaJWG4ilfbdWNY9t04RD1CkmjdNOanspB/QQJ/ytOmrJrg/4TOQ/oq7WxVGff9co1Km6c4naftqIQqANB9bhKPctxfaBNlTJcYEVTKeyfbWoqlUEb1DLA9v7YapgMgAV8qfOU9/RzTq8A6tPqyZI/lur7CNReULmP6plq3ilg6nl6mV/ZSX1yWJVUDuoMh6FyMYOmrX9ilgpbzX7wGJ87FdytuC6eYCCgdDayfxIJBGoPqBD1W7IfzzHdoLQHDWx2eSxaHVSuc5eBcFHTdeMYYDtWPSqLpZLFk7VR46tJnxKoPempNIWOKRsHnXKr71e7+p3a2dSm5qRa3JgHCxP3SgTNA6st5VfA3H9ztVpBIYGKsCiOIlD7QeURuc3klnI78kobJIOEqTSpnqCqxlLc8vMgHh9qNi+j4sizmOWnCKh741R+ftwTBQRqL6jF3ojY9MqcumqfWflw6mslnGLA6VIo33XSsoUycC08QSivqoB8FqlTArVX9sXiiJQ17D8P1qKvtBz4l71UHmwFwfUKu6gaY/7i3N/OK7IKUHeU5idQB4Cab+NJWejVQXUx5+/EX2eVpH+OKos3M0i5ih3SrQrVFXUEYi6V2FOVoldMZp9AHSDzk+LUDqGEqg7qWh6Slqair0TrM/CabpZXKAxETq0WDzWvxuYeACz+e7FfLHkMRgqVQB0gf55Ao4KnCEeoUZNKNcGxjJ2n8poJy4lF8b61WFyviwCn9bNAgiqWpjbvqwpEXiAJMGVF+08J1EGSCV8RRqVgZYrbdK4ESYHNUxnVL0/WZvP1abW8wjGTKF8xS92BXaqVy9qhwb0E6mARGX8s9AsbnVRoJcV+/c2n8l4TWayHZ0xwRsoN/9rTtk0nYjiAHJYual3LJdWMMv0E6oj8VIrLJUHJNWvU4A8ZbT19skqszmaLYLFYLBfoO3DDrxt4QapcibqwHGaUU1+Jid1UlJsiUAeH/Sn3UBHTZtsfXEVJaexYq/+yrP9aiO4RHkPBFPTl0kQflnNanghUYBpgB5ZdAtVLLASVgn4CdWjYD6DiBAqsnm4AFdagi5Mra1FeesZBXWwExWwNSAZBdYP6Fc6koB6VeeVcFaNYikAdIUdYycd91EhW+TeHP2ashp2uIXa64tYTrkHNl1RxyoE2TZPjutYRX3NMxdo/u+qiwtfJRSVQR0RTLLa8ULRNNZPquYY6qnc2FtAIulTM6hVpVlC7WOZnm1K1Ju7axPy+alcp1VUlFs1EI1BHOali7qSkNGxTqa5rab2pYu6ZKi+B5dLXpZmKIpPUYZuXF9vmj0hjPH7C06/ULMdamO4ny0+gDndSET8Z9bcbf9CYeht1nLdXxbbBVa6osxL7JVLtEamQSqGqrB8ky0+gjnBSRTdKD6iuDIsgEZU6+eITsPWY1ypG+Oc1J2kqelqRW8erdqfQqCkCdYyIGRSWp8L+duMPE6nswuDj1HNzESQeTFkxY5bzqYmD/wHPesJfKtTTP+j2E6iDbb+I2kUetT2ekvVPnFXzxcZJUrZlGonYJc19WwtGVdU4zXmNTQ1UHFVBjacE6gTbL+ZPSfPfXQDVlsBiSoUWC9FyTh1nXR9KQaEUgTo2QQVxP2RSW4+n8moSV1O5xWcJ7kwtRVlO6mgKtVxRzaiTn0CdlqBijjqc6gqoWkXOReeRli03TKaO8k/RRTXrnX6n73TzCdQpcb9Gqjua1DVOrvD59xov2F+atw5gd6t+SZNG+BCok+P+FEunwzCaRqrnMbkKgH9zaJxtkeuXA1RLoZQrVvxRJSqBOjbuP6kJVALTScYfTq6MQikb/ymW9oqkvz45DcumqG6KQJ0aTimVqpJUY0E1nPglkaQaXMw84IfS/6SUHqBIikCdpFKdYpR/NJXUxI5TMwkLMcUaAKFQkyLVj1+job0E6uQMFSsg81raUrpVqsMMDdSQyWRVqhRqkgQ85mLc7lMKlUC9SaXqKarRpFowuyrKWfVe5EGrFcjOU2i+FhE/OagE6iTJnGInqjD/U6w/DEsJc9g9Q3Bqe6BKwfoH3I/FPABlpgjUmwJ/cTwFoHreeFJlLtWV7VeJmWJ1lbgM7gAW69EokCJQJ8vWKWX9VRX1SJ26hhJAy0BSDRPLAK1EXUTtmiZOCdQb5CggWhecemF3gUpTdZVn4/oTGwr8oaWPmddEVbNYMQ1BJ1Bvlr2j16YoTkcdUqECNpkq8Ec3AOIoTE4Zqr+KOCVQb09RyWRqjulopeoGCS6ljhmzz8o3heYABzsDYrL7BOqN8v0kNpz4nsYpfD42TRUErmcYRhGNBYvFi+pJIU4J1PsY/5SV7D58EkXjgiqvLK6bb1elvBSBejfjn9qe1paC2Sou3lhQ1SeuZzqq74+G9ROod4z8U8uLVEQVKlDHoVrkq9aWI3b/QhhFldIE6l1E9vinpqeBGikZmgDwcl81+UNgikVUJzL7BOp93VRHjKLSLX80ovYf7T6MnbJYXuXvOLRU4q8K6lv5r5e7PJmt9Ca5Ti2S/jmqwgWow1r/kmFaLNVW9ZB3+pcEVTH6eT6f7/d7/vFu1Z0yoHJ8r/BRJaiR7gSoY9F10Qa9xqGTnmGaNjRNaZNTjmT1/6oa9ft+u8uOp5Mk4XQ6Ztv9XYxrJi9paOnUqCqhgBWgNISYIJb1ImanlXb7EaZ/VVDnu+PJ0ebnKCJOx93+b7c+nb8VpCrrH9VBlQD7tpo7KbuiY/354HPakdH/a4I63x5Lc8j0lY3pPcD4l7h+7BhuVMT9YRVU+YlfTECtPyH+ZP7/y0i9KSFQu8Ly7FQemVcys4KS7EZU/12mUzmpXqPhj0pf5KgWdGpPh6v3/2650dotf30bBkbxadO/FxceApC44uUylriGRw7/5ov8oc2intCQZ3FRz//yKr73Mv0NV/x0/MudQP1TV6aw4YHzwbSJpSIPdHuMPVc/RtZAV/VpRbwQylDS/DlwTZrt9r9qNurtpu+7zPfb7Q6FxwTzm644/O3wuN/qIRoVMBUTHZCIjcXDF3+9APnDtGymB9q3adV/SOuPg3i8sBNTcRAAYZVpP8vT0o5hPXCjy7Lv8XR6Hl9/QM9b5DLyGeQczLdFbKCCgkx8cy8nl23WLwh/H3fz+pV22wlaYb+rXYZf6A6g7o+FtY+ZZXqB2PgQwEeRHjJfnALVm8qUvh/R42WxCaVQUVT3Ukt+QBFzncUTOH5vCwNPTk069P88qz+8dMTV+ICs676NfAYKm/3u6DTLaYBS2J6coXLKELtmVD/L9GHXSzLMaGbO6AsNA3VXYMrMdZIv0UkQ1AAq6IPrYiF2kNxu/387OsXkfS/qkSKJFb6kHVX885abve/zQSqSvwnnzQCc9vyWdmffas/gc3eapRuungh264yT4/bSguqu7Vt2o6z/pf332d4EqnbHXv6AnSM40IGrsShZCIENz9frcrn4w46dO9TU/ZnlfuoAUhFWsVjlpfVnf26jxDldmtVH2+Nzslu13FhkuuYM7LMhbO3bDfbcGS0tanrvTACsQTred+2vxABQt/nEUdtfLIKkqPiMgkUuS05rwk1wvhTCyf737Zn/FAdGhp3WX51WoQcgsg9Nv+/81P4qv426wZlQgHNn3AU77tC2WaXywDobqgb3bY7D1pki2aV+pV3H4wf7qT1PqO2lGwCqfHqxY5uHICgVJUfuYsnVqJRgLY+JmNSqx1vy/+LHMjHa1KskpZr9VBCY5JPGaTZGH2SNL0776ylV8HbkBTvI3rUUS4zwLlvCgksnXl1adTvUcRH3erDxn5+6f4upoO5y3/RgyiN4vX4eXFOAFJuTkjX0gCTrF0XqnzeT6jjGWqHap05Bo7oWdEc17TrbdrzII2/wvEfBtIA67q1yaY05xijVt9fMmSg1pZp1q8KBCvXoPARUxaltHMxDiQmd1sRbJ7iadAEBFmwvFZmsm3o+1esiKk+8DoVadAPAxqm42dkZB+prF6j7HlBbhq+O1On701i0dncFtUZ+N2L7YZz2KPhsIqiqnMmMDubZKFtZpcQiw/fXXgKrnsERgEDdNWXy/4Y0Vf4Ss0SsmfC81pjf8/KWFTVoYjfcNRqtUd8F1Ckm+zivXugWUKtqsvtKx8sQ4793HgKqurlnzz+ffTnBtEQp1Ib4vmGsA3RWcaEuKNk1u0NCVbwy8UveB+W1khqiC4C1f2JGf8W9Hwvq288GdSJf+4q3exuoZUucOdOstv7+Pz0E1H1eHgqgRtqsvXx5aegfDhxUN4HlelIEqWMsQov8U55RaaPNm8qpQpmcKjZH15Opdwf18lhQJ+O1L1/qRlBLUXjW+6P7MO1/MpNAFfFZ7ACih/NBH1+qhkN5PkgoWz4VqVf4i9GfIxwSIULiPzbKFf1h0zlq/q+R3TBc8u6mv+tFvx3U7Ba0LmOcQmc4fX1Pqi/yH5IqmwRqJvTp+eBH0vJHGqKe4tQoNGywuIqcKpAqp5DfFFDJUT8sqDSeeFqrSmXuX2gYrI7L2/2DqYeBeqMWLKUibwZVOw7JRjkKozNTk0GVkJg+B/Vgmn4lE9TAKZAqsv8B5AKsO4zN3consVYN+73zKGE0at0UPSCYehSolzsqwdtB1Z5b/9tnfktmaiqo/0ssf7TBCTUUqOV4H+1+Gd0kJxVG66Ydt214QJWmzFm7Q2amBng45gVW7Qd/HNN/O1q6t3X71YrQvx/U4+XzkIqR+4Iq9z8dDhAtnU3TqHN64P+rJVV56A/Bv1u4qTep1O+nlAdHse3261I3Cdw1ugJNP/juwdSjNOr2VrJ0Z/EOoObGP7uBs9fPvZmpiaCKqWUON/wIKgT9FcPfyKkgVYDqyW2Ot6nUPVYPQuTf39YP49FCyLfa1R/89mFAvZxuBlVLCt4B1PyANxvpdow3/FNOpvBVTW207v7hfD5EWvI0N/xNB1XC+us5qvmtxh/S/v3DJwBT3wsg2epXX7aPA2rm3EHm9wRVqdRspNsx5QBjPKhiTRlEUhJUo3xi6bVxCjp1uVgmXqFSb5v2KGNFs0ejejzc9/1kuUjgGeLs6ZJm+SCg7u/BaXHBe4Cq6Mlusd37kU98MKhHTAsJw4+g+koMnFjWzikkVBeyzMrHtqrjbd2g0ls2fCh56cR0fV0ur1DH7YmD1NNvD/NRHxP1DzSQw03wXUCVajIb9ZOnGP4JoM6F5TcK0+9rYngGOqih1yfCWbwpnJIHVLEZwlltidREZlaRUt9IsNZA1CKKjMP+owVT2/twyuPvO+W6NPiyMVRPrFwYDepeWn4JqmmWQIXoCoqporAHVfec3m77xd2LrWUAXuh6vVZuMhCK7xvE1L1C8TaIF0ZSpe4+GKjz051AVUmlu2hUafuz6awNdmhGg7rDQylFZ1Wj+meTg+o3FVNVxHBuj/tFSpc5gSjOMgzDr4gBxVuCUviQ8Ccmwqnc9r99BNN/H6pKEVCXRs1U7zWX7NSd7xoT5tX6Fd6GZzImgcpd1BZQDyYcqYpcUI9KFeWhN/bZi22pZpBcl7MZKFahR4Wsg8VytlwGicsxlbafv4HKTsflQ/iogxTq6XQahstbD6glh+yy7aV+KKin+efJJYujQc0wfgEmZTB1LoF6xrN/zksfqTLuv81JFbc4tgJM6ou6Vy6zQgBTqNiWnYZeFHpmJeHw64PaX7RxgmF0IPtdb3By7NWo27diQtBbt3nej0qc7aYa/gnpKfHr+TLq9yugnjUN2wOq4KWjUWGOowG5wCyDlhEn/xI5iERu33VBc+aMLq+irQANvwAV5lb5EoEPZPpf+/qi9VdnP6jqrhPU4YfG23EZ3nL/9/z0MFDVbTproB5aQO0h1ezKpM632bGqMxpnAsLTYfE6KJ2XCpGH/FIWoh0GFqqycgz6AYpSujXPca5N3MGxFMd+Kzoc1J526LcxoOrV/uMc79EaVQbaRhOZtbRqkybND1rxBDRrpLT+Qqd1zaHZfjPQIYWdfAn+6Sb5TAw4awB6ue239QTV5dcHteeOZtW53pcedPA92g3q29Dy+5GglngbdYSxm5RHjZkA9SCOpppBrUb+kNiUcTmqYwS1fuvmLXGmmM1XHb+L1gOc1ETTpYJT9YcUEU0FuS7fTgP1889IT51G+H0DopT9SFA7PI/dSFC1oGRcxm036WSKpWcVTp2h2K9Zvxp+oT8BU86xyR9wgIiL/8mqR0QC0xKccntpmivVKqr/78hDu9gWWlQDNSlTWoinnNTdAFB5dHK5XDBKkYMY55euXuUHgbofHQ1393bATf9ZoKoCrrFF4BPP+h0mOTU4dTmotayqVjtt+Oey+Kx+XKFDAEV8jNlWPti8uDf692QAM0ukoc9RDZoxRVAjPJw6DqieOzWJ886gdsb8rbUe82N33P+zQJUK4m1s7cJ4UIXDghkqrjMNVKm55a+eUynjb4AuRT0qH80/2ngd7YX+vksdOXuXf7Qtc8GD9SWkQhcL02KoWPHf9WEdO5h77qwDGfcnbYBKVRu4qjAlH0J5r8PJx4HaF3WPLvaYjwum5vfzUfPU+diixQkDKGRLP/NDpUZzUA9cu5ZJFeeZBxM5BQ2LrdXYuoKgxgWo21Mx+//FPHhXee6JTawIK8vVavaP/Ltwut9aGHzcGt2FaqJFU/MPAmqXQjtOa+zcd0do1fTU9l551Nz4j+/+mgDqdzWj3DRC4ZjmB6pcXYblc8yIu6lo9M2z78lGUQmqVTp0/y46BtGQ29yZCNQ0QIUqzgTMx1eeSpilJihLnCXodqpUCPuj0CzVpfz6oJ4mKNTOaX3bPlCLNMLb5zsm/IvLj37Rp4z0UZYgZib6pwdFKgfVqB64u57ENCx6/j1MCJgxK/JTakxNGrNnuFqwFANWoQgqWMripwC0qiQ13mrpegRVYJr0gxqJgpjtRwF13ndu39LikXXd9eEadduX6RqtHecTamx20/v6xfRn64wFU+CPGgJUv1pOhceqRWGTHPgH8/Xye7fNVaXpAfCh1l/iyYNRWVoCy8sxFbAtadSii68bVKie9lP2kUDdj797PUduWTeo2T6XbfeR7BFPmsaCepzQrTBtSFoRUmJsbtv/aWBgjwUhJUzNZ+DUEK32OqvQFSLLUrghUDkoa+0aGINFalYPdx2us2WuUzmqayb3R6AB+7sAVeX7k3bvtADVwJ+8+yigbidZ/i5NfLxXPeqoMj/t5zvvBGopoYzUMNNw15gH0LNTvvntmZt9NeVHPwLgfqqIaf4OFxPLS9jZcyGRUBsKuBTTVrFSj78h1L6z7etcgBqblePTjqgffjbTD8V+cVC7iOqpPTs9HNQxhdP3eEuMB7VW+pA6luEfyuX+Buf02Ww58w9VVwiGUWDObT+KUJ+6FVDBpAOpsuh07ZmFRvk7RmBmbvm7OU3EWOyPBWo2xUXtBOh0J1CF5f+1QYWNHOV3bMrMQ6mUCjn95nte2FhH7XoM3Vx1FWvN4xxAvf5IFxsDlzgWeA2V/AWpO9TFxjCNGrwDqPc+6++4XnfZecc3nuZD5pINPg/9xUHFQjz9YJ7rxBKoilOvsdwf5kAiZDLHb8LME0gcND4WPyS5XFdSjX/P+PfHzlpG/EkyCFRbLzP4xUF9nQ7q7sGgSoV6x/aDx4CK3/ldwCrW46ZMS0+Z37gcotaCVNdd48pn4XCaCCNkYpsfC6GaseYq8woTVxbLlYjkTqc4ZTHLOe0jNcD9lBqol18f1OO4c/4hYf99QN2/fhCNqtXlqf3NL3nC//ztmXNqtFelhkaIM/0xkBLzToxmhcr/JZQHXXLWKo+szNhBbcxjsNgKCmXb5JjqoIZhRKDeBdT8x38YUPXYypZIHZ653T+39aQYsqZFjp+OnyM5VPXQDLbohQIXQJ5TLa6BJaZXIuZQhdKCai+ouw9s+ieCehfTX9TDfCRQ87MlMeUPEqjm8znyG0FFTPFRtnA1LTlmjX/dcxs4FbGZG2CziUCVE8hk/R9U+LdrVI3UBItSQvRR048C6tuv6qPuXz8mqPIUgAGpkEE1TVGhUhvvn6dajVCUMDsbCadRhPxuMZRXcioPqoLFVRYAJOdYKmS27jT9sqZK/Cuc4PqMfRzT/9aZZZqYnrrcDqpWEPDBQEVSU1g8BcvPzLMpyqsqPf6GVqhqYDCVMqVF/SKU0kGVnEpSF4rURCZiHccKVTDVmDvNKwDgI1xPbGb7IKDekPA/PjCPurv3+LZ3BFXN9reBBU6qIeunGjAVGNqifv8smQwP/kHMM0cqG6dYunJ3Bf+QyEpBaDX0WutRklJBNYDKn5uWR/0AGvVXPELdDdLcvyqo6hU3PM7pc73K3xMjACOJHFeIEAl9UygbTcl+r9LQKtP6HFUXr4Bese+7zaf8iTT9+d9dzunZdD4QqBNWVvYmiLNbQd29fmhQ5T2KLePZ/GbWQcWC1eLvTOjfPNVqNLVYG5XG69IWFBu81NTgMBvB1W2oQEk0HxWbAERxrPZi/wrBVA+J7Rx3naG+TS/z6433t68fG9Tc2piQmlIH/trEdCisLhr7RcheYMj/3WhUqI2cykW8cWwHUHFlLBaubu+LJr/cK4DPfDzmLYH6jmf9p+ZGvB5QO7o2ugbNdDY5X24A9Th//fCgyt/eNp9NxamhbaDQs6RiDoRzLkiGOtQGTkv06oNPfVHvB2da8KOwb7/QpBqnst0/CFx8r/C3SFGP+gDT37PVd8ykgOmtKH1rht7eZ7v0mIK+4/EdQRVmij0Xll/OSzMqnIru+tSKfN0zqB5IGbUjAG3cuYlJBhuWniGpyWxZapd29ZQVJGDX8jmIvNa+H9QpXag9vXhvY6JznJLf2V+0ndKJAu+XqTurssuINJhzGjF/+NSpMu4Nqnxi376dyz3T0aGiGj0WM/5f6HeB2j5m3fANVMmpLZbzic1WC46qq5375yYfpv0lovs1VBsn5r2gnuaaXPgdwh7/XV8OfNtfxjG8uenS0y59aevt622XziYajcsoUOcjrvyuoCrbr1VPhw2bUjBgj2PDKDKnXh1Ko0p3/g9cUaOPy3xRXOViRuEAqC6C6pIpTulygWNdfFiKJU5QT58nzZ7q3dw3YPrduKlr3Rc8tnC667npU4PI+ujIblAHe1bZ6/uCKl7UUr2fIVxNX1/z40J5f2x5Ob5uE6htChXHn7IY17EWX+TuJ/9vscBJfnJ6L4yi5JSu4cgWVmLiMOyhAygeAGpWV0hdjW4DeuCzkfGZ0z/SZ1gpyhBQj92qvVI58K6gytlUpVL/EDKkvhdqmyhh4HTKPAWn6zaAiiVTYVPZFRcYW5lCqr+Upj1gtLQOBKzYv7JYq41YPixFD8PQKN/gu4Pa2WK5rZHacSOF1u9xJ7NLbcN5N6e9Q9L6zk7HgPo20PhDW9G7gipmUznliSmyzFQ7TEXLb0IqwMgrTmuJqMbEqoepBNdl0GPlG25lF5sS/KnPXM7q70aIAwUiGUttHwZqtw7ZasP3IPeUDbDrPWMn96o4+FXMn5xn/TqxC9TTrrObeT4G1EGro6WleV9QxbM2q6BGXtGFKqbqpCbmrEK3MP0HvTAAyQ0bTwAMHFj9DEeurltub8ExAwimsPbig6QUxavMur7zIN/exE8pbt6fBiUPe8xnpru+892pP4nWM9Kn851xHL6b/fg6bEOPKBl8X1DlwjSjolDDfDM5uAA+4/G6i96mNjGVB0NhsVO9WaHKvYBrZvlYZu3WOrFCX+nVs5guiAkyhSnEUqlTVFPefeJ0f3PLaSfnZzcNgm263gCldBQzuS/zbdY322HAaPQev2BX8TX6juL656H1pkseAKpcQVmZQxFqxX6cmTOLxV5oQxWo8H/2lXlGUlGhGi2cYsYL4vzG8lXlyOoFhjmn0YNHow+a/HmCke/9j7qMmSV6Og24pHbQ0TnSp/sH7sdo1AFnCzLEfF9Q5cY0XaGiptSL/aDQzsStaQpU+HdfWGhg1XMbswBuKQ8Q9Y5f9/QxAkqhnkvLAx4A6ud7nSnedx9kmf4eULu1YGXYZW9xQ8/7TF3ufUH9U5izQ93wa6CemY2KM5QHqKEAVXkIIeDbYPnlGJXbQLVLe4MeoVHvdSq7H3RwPzpof+sHtTfTUDL+/VU4+0F5hPcFVTxtVjipkOoPS6RCBRNO9UMDrTgVoEbC+BsIpdF5UjUG1KggVWxh/fP1UcFU54ySUcUfA3/qyIT96wCN2vvW2I7SqN11Kzn17wyqWEdRclLDEqghjFQtXM5Qcgqm35ecRpzfBlDLSrYlzdqsUFXQ750fvGLyfp3upcKAe+2Y3A74PbYDArj9IFBVJPC54+kP2U/zEFDxOaUsP0H1ledZjJ8+5Il67FWJkKMwwqpqIUYEfdcNCtUo/3UoqHl2KqxtC77zVpS7YVU5xr+POzHI7d0OOGY4DmpFyQYUh+9ffxKoMm12NrQhVCVSwfJHJVDlcF8NVJhCZfidClV882BOBamh3L/+z8eCeg+sqpVWd9mDPh9iGfb99VclcoaA2vqg7PWngSpXUYUaqIpUYBUsf154akg2cyfVKEBtOvo3KudQxuBQSmjU+nLpx4B6Od5Zob6O3c7QcruHgzrc+O+GvIItPq/+a27HlRjcDOoFr8x0TgtQw8g4n4sj+lBTojgJ2Nc47Tv69w+HQdGUuLq4LqucAr494Aj1Lljtx/zg8QUlAzRqz5FS4VsOArXldd6+/jxQhZYvDqfErmepNqMIuuuikpZUoEZ+F6i1Wqr2CUBNqalQKNS4Ym4eBeqtWGXjSkxHRfwDQe17t+XsDAO18elnrz8TVHE4xSqHU4IWw4BV6VHppAnzUehAHhBbdFyNJlCNcvr/MMT2qygK/2NpBai3x5h+fuHjvZiqjPiYfs39wN6/7cB323Z4eqrF5y37N+8Oaj2cykmVoIZlUMEhMEDj4sP8HFSjCqpXBfXsDzP8QqOGNYX6oPTUzZH/fGy/3lhnYhioPb/Dvm+Q77Hnld6X8HvvYEptgMBUaj6EGhxVBPX8bCpQQzXbJxQaVTQAyvkqviwn0ZmuHFTBNrahZ1LgdRhOWnf/HgXqLW7qvnPExz2uOQzUnnjqOH97Hd58WO9+qdD3/qCK15Od1dA+sYOC/x+c1bPJQcXwP3diVZYzNHwxtDoSWVWjMgzIqPT5YUbW7clMFRo1FKutjuUb9iDTP7AQc1Bm6h6klpVXZ8/UdhDOBT6Du2QrFuF4GTrf4FGgSpXKDKUgcb6vmB1pwLaf0to0mRMA3zSSiwCjBo1qVLOmrhfANrYhdh8VauiPxOk2UKeTuu0YgDKR1NO+9ntkg35+r/EfYforXnZtPsBPAFX8eqkphk4UR1TQloIatQwqkhrlGytlZIWqtgRqWKmSDtbPoFLd/lIUAFVMRK94qA8EdWrev2ei1JSIisdmb2NAHfwrHC8jR8Ooqu7Tcfv6+vNBVT/TL0BVSBrm8/M5NErbU5DUKF+gJnIA0icoHZhqa9Xhv2Thn33TayVVMSpKB+WYyuHv49tB7angb9F9lyGNvqNyXZeG32OYRu0z/vvRa2D2++12v7+0Q/OuoAq/JbbDw6GyGd0HUCucQuAfFWWB9jnyjUj5BHrQ75YHUXjL5Oy3q1SdU+5KOLVDqUeV+ekKcGRt6nE+IP03Tqmeto1vuIEatcf4717no0CdtmrwgaCKkDc1/XNlMzqAalb3UPpilqr48oE53FmFw34DS1ML0++pqal5y/6SX/9suE2oFuG+EGH48+3nA97H2VhQGyHbjlGquwEv7ds4pZrNx3b+70f4L9uRoA4ww+8LqnodOKlNoNZJ1cSGHetcBQqNqiIqNP24ckqT5fXASQ3dHv+U6+X/iFuU3nzki7Mfe1uGK9VsP1gPDFWqx5ZLXjon/JffF8ce09/1Vr+MbQ4ZmbC7HVRlMSpb0rgT+vz87DeAyh1T8dUQ1p35Ij+FXm0+vcpwveoUFG78D9oBQj3cF6DKMtRGJXkcczrUlXVvjdaHYXXcj1I/Q6553E7AIqvOHZo73e/N9ldkP8FfHHMv7gGq0jyxaZYXTx6ezWc/rK+h1vxUBFxW/SGrBagVUr1g6Z0PYP3bOYVWArnq71gz/K/t++ibX+X2x2c3acBsP/oF7tHUp55L7gYzse1RdNsJr8i43Nu+aWjXnUAV+3Sd2KmA6j9j2N9h/Y2XVJEK+pTDGqpq1DKlINflWpDqNpp9UdwnA6mW92WjF9mh35q9zp67su9YKH7KtvNJVqv9mqdj/yV3g/V6S/Li1N0klo3/hY7DssD3BVW+EKlzBndTW+ULm3z9Ti9V1AoUpVeQ6g+bQVWk+nmWqoopcBp3n0xud1lZdp3JzPrjB5HGv63e0Hw67qZRKiLo+TarXZNfErv83wY8oervvW99n2U12V60K2VTXpEGJVD/Obttl6N7D1BlOBgDqZq+PD+b3w5dmPoGWurUwkVAyjHwaqDKDMCV+6nnvA+rhmmYc7rrv3UPFPGz5/v9dsdvxvF4hFuw38/vd01xV/fz+ajv/uByF1C/H9HkstQMtRaqw/PzN7NLoXKKGU6ltAyZZsWqVVyKljOqZaquy6v/fIZpfaHmnoaqsPUs7H5twId+y2rSc4uFXAp5m47G2z3eANMumf8a+a/zOuQlavidK69G/0vYJpfqZXoudBdQc58jtkJNqT5/+/bcbfo5XLDnNH0xCsEL6JrULTb6LLn5P59xl4Wh9CiODvLPh2cnnegxPUq1qtd+8s1swei+l/wraVSNVGaGpf3o525QlRpkhperVCNXqV6JVPg0WAaGIDUf5gdnXPxL3yZ79iR/IVBf/13mUFLHMnJUTS5dKpX/q2/LtXxmUQ3oi60q+lY/t3E6mmme5ZS0g7pM9hvdUwJ1UBIEd0/K41Jc7NeeoIJFEjGuVXfSWAJuiAkVvjr9L4f+YsYEJmLlFD/4eDjnnNIdJVB7Mw4yfZKmDPSoKJ6GAdBGcyTFMWW40y8F4YAboSyw0qaulBcBq8Z9HDBpqJot48zS4UfoJH91UIs0bgpaNQxFmX9zPMWDdMAUHgvRlPAaTDG2XwzxDaOwJMUklDCSg4Dl6EpzWIUnCYFaNf9A3csZrLj5/Px8qFl8wzdtB20+fDgpwGPbFJP7fdldXSE1nxmgV6Lk6rTrXIOEQC0r1UxD1bGtM5SmPB9Knf9cl0pKxaOyYv1AGttn6YCKDTzFPItI06xhAapvx+nwCk8SAlWJXpbB/U/GbNvO9/udOaPMkQlPvUgj9xpirlWh5q/kpoIX4UfCf9V6+bjCtuVhFLmnBOr4oEpDlcdKgkrGxZGmXjutLs6cc68hdmxTzveVulQEZqLhyhCDJWE6QHS2c+THlc6REKhCq6qkaqoBy6VWRTlvVMVcD1uGK2apGeUWVvlXI/LPNssvfyJ1SqBO9FX7dss0VVFqZXVxyuxnEzzVUPdvxciK0D+/MCdOu5swSAjUIfLnhMJMHW9QwMw2z34p8vf9mpc7vhKZhEAty6WhMLO7LrOsidG282jMskzTsqwXmzNacSHIOSVQ7yN/E1WUKEPKMuvbw1IpeIY1qgmDhEB9pOx3QzqPp/Z1kBCo7+PgEqUE6q8k0CXUAulu/53uHIH6K8GKTUKwT/QEK0CP2CpEN41AJSEhUKdJuTfoQneMQCUhIVBJSAhUEgKVhIRAJSEhUEkIVBISApWEhEAlIVBJSAhUEgKVhIRAJSEhUEkIVBISApWEhEAlIVBJSAhUEhIClYRAJSEhUElICFQSApWEhEAlIVBJSAhUEhIClYRAJSEhUElICFQSApWEhEAlISFQSQhUEhIClYRAJSEhUElICFQSApWEhEAlISFQSQhUEhIClYSEQCUhUElICFQSEgKVhEAlISFQSf5y8j8Z90qVOfawlwAAAABJRU5ErkJggg==" alt="HUORM" class="logo">
  <p class="sub">Informação farmacogenómica extraída dos Resumos das
  Características do Medicamento portugueses. As perguntas abaixo são feitas
  à API pública desta mesma página. Cada uma mostra o endereço que usou, para
  poder ser repetida a partir de qualquer programa.</p>

  <div class="estado" id="estado">A carregar…</div>

  <h2>Perguntas</h2>
  <div class="perguntas">
    <button data-url="/api/cobertura/genes">Cobertura das guidelines, gene a gene
      <small>quantas vezes cada gene é exigido e quantas está em falta no rótulo</small></button>

    <button data-url="/api/cobertura?estado=ausente&limite=200">Onde o rótulo fica aquém da guideline
      <small>fármacos com guideline publicada cujo gene o RCM não nomeia</small></button>

    <button data-url="/api/genes?limite=40">Genes mais mencionados
      <small>contando alelos e diplótipos para o gene a que pertencem</small></button>

    <button data-url="/api/seccoes">Onde é que a farmacogenómica aparece
      <small>distribuição pelas secções normativas do RCM</small></button>
  </div>

  <h2>Procurar uma substância</h2>
  <div class="procura">
    <input id="q" placeholder="tramadol, clopidogrel, sinvastatina…"
           autocomplete="off" spellcheck="false">
    <button id="procurar">Procurar</button>
  </div>

  <h2>Um gene em concreto</h2>
  <div class="procura">
    <input id="g" placeholder="CYP2D6, G6PD, SLCO1B1…"
           autocomplete="off" spellcheck="false">
    <button id="verGene">Ver</button>
  </div>

  <div class="url" id="url"></div>
  <div id="saida"></div>

  <footer>
    Dados de uma corrida datada do pipeline, sobre 5 565 RCM do INFOMED.
    A API é pública e devolve JSON. <a href="/api">Ver os endereços</a>.
    <br>Dissertação de mestrado em Bioinformática e Biologia Computacional,
    Faculdade de Ciências da Universidade de Lisboa.
  </footer>

</div>

<script type="module">
const estado = document.getElementById("estado");
const saida  = document.getElementById("saida");
const caixaU = document.getElementById("url");

const num = v => typeof v === "number" ? v.toLocaleString("pt-PT") : v;
const esc = v => v === null || v === undefined
  ? '<span style="color:#bbb">—</span>'
  : String(v).replace(/[<>&]/g, c => ({ "<":"&lt;", ">":"&gt;", "&":"&amp;" }[c]));

try {
  const r = await (await fetch("/api/estatisticas")).json();
  estado.textContent =
    num(r.documentos) + " documentos, " + num(r.substancias) + " substâncias, "
    + num(r.mencoes) + " menções de entidades, "
    + num(r.documentos_com_pgx) + " documentos com conteúdo farmacogenómico";
} catch (e) {
  estado.className = "estado erro";
  estado.textContent = "Não foi possível falar com a API: " + e.message;
}

/** Encontra a lista de resultados venha ela com o nome que vier. */
function linhasDe(dados) {
  if (Array.isArray(dados)) return dados;
  for (const k of ["cobertura","genes","substancias","seccoes","mencoes",
                   "entidades","documentos"]) {
    if (Array.isArray(dados[k])) return dados[k];
  }
  return [dados];
}

/** Uma tabela a partir de uma lista de objectos. */
function tabela(linhas, clicavel = false) {
  if (!linhas || !linhas.length)
    return '<p class="contagem">Sem resultados.</p>';
  const cols = [...new Set(linhas.flatMap(Object.keys))];
  return '<div class="rolo"><table><thead><tr>'
    + cols.map(c => \`<th>\${esc(c.replace(/_/g, " "))}</th>\`).join("")
    + "</tr></thead><tbody>"
    + linhas.map((l, i) => \`<tr\${clicavel ? \` class="abre" data-i="\${i}"\` : ""}>\`
        + cols.map(c => {
            const v = l[c];
            return \`<td class="\${typeof v === "number" ? "num" : ""}">\${esc(num(v))}</td>\`;
          }).join("") + "</tr>").join("")
    + "</tbody></table></div>"
    + \`<p class="contagem">\${linhas.length.toLocaleString("pt-PT")} linhas.</p>\`;
}

function mostrar(dados, url) {
  caixaU.textContent = new URL(url, location.origin).href;

  // Detalhe de uma substancia: sao tres listas e nao uma. Mostrar so a
  // primeira deixava a pergunta "que documentos tem esta substancia" sem
  // resposta, que foi o que aconteceu ao procurar siponimod.
  if (dados.substancia) {
    const s = dados.substancia;
    saida.innerHTML =
      \`<div class="bloco"><h3>\${esc(s.nome)}</h3>\`
      + \`<p class="contagem">UMLS \${esc(s.cui)} · DrugBank \${esc(s.drugbank)}\`
      + \` · MeSH \${esc(s.mesh)}\${s.aliases ? " · também: " + esc(s.aliases) : ""}</p>\`
      + "<h3>Documentos</h3>" + tabela(dados.documentos)
      + "<h3>Entidades extraídas</h3>" + tabela(dados.entidades)
      + "<h3>Cobertura de guidelines</h3>" + tabela(dados.cobertura)
      + '<button class="voltar" id="voltar">Voltar à procura</button></div>';
    const v = document.getElementById("voltar");
    if (v) v.addEventListener("click", () => {
      if (ultimaProcura) pedir(ultimaProcura);
    });
    return;
  }

  const linhas = linhasDe(dados);
  const ehProcura = Array.isArray(dados.substancias);
  saida.innerHTML = tabela(linhas, ehProcura);

  // clicar numa substancia abre o seu detalhe
  if (ehProcura) {
    saida.querySelectorAll("tr.abre").forEach(tr =>
      tr.addEventListener("click", () =>
        pedir("/api/substancia/" + encodeURIComponent(linhas[tr.dataset.i].nome))));
  }
}

let ultimaProcura = null;

async function pedir(url) {
  if (url.startsWith("/api/substancias")) ultimaProcura = url;
  saida.innerHTML = '<p class="contagem">A consultar…</p>';
  caixaU.textContent = "";
  try {
    const resposta = await fetch(url);
    const dados = await resposta.json();
    if (dados.erro) {
      saida.innerHTML = \`<p class="contagem" style="color:#a33">\${esc(dados.erro)}</p>\`;
      return;
    }
    mostrar(dados, url);
  } catch (e) {
    saida.innerHTML = \`<p class="contagem" style="color:#a33">\${esc(e.message)}</p>\`;
  }
}

document.querySelectorAll(".perguntas button").forEach(b =>
  b.addEventListener("click", () => pedir(b.dataset.url)));

const q = document.getElementById("q");
const g = document.getElementById("g");
const procurar = () => q.value.trim() &&
  pedir("/api/substancias?limite=100&q=" + encodeURIComponent(q.value.trim()));
const verGene = () => g.value.trim() &&
  pedir("/api/gene/" + encodeURIComponent(g.value.trim()) + "?limite=200");

document.getElementById("procurar").addEventListener("click", procurar);
document.getElementById("verGene").addEventListener("click", verGene);
q.addEventListener("keydown", e => { if (e.key === "Enter") procurar(); });
g.addEventListener("keydown", e => { if (e.key === "Enter") verGene(); });

pedir("/api/cobertura/genes");
</script>
</body>
</html>`;
