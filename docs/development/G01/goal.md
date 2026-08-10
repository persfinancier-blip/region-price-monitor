# G01 — Автономный мониторинг региональных цен и остатков Wildberries и Ozon

Canonical issue: #30

## 1. Goal

Создать единый рабочий парсер регионального мониторинга Wildberries и Ozon на основе существующей реализации `region-price-monitor`, локальной реализации `C:\Dev\parser_wb_ozon_delivery` и полезного legacy/reference-кода из `Price-monitor`, который автономно, без регулярного ручного открытия браузера и переключения городов, получает данные заданных товаров по заданным городам.

Основной механизм регионального контекста — мобильные прокси, назначаемые городам. Для Ozon отдельно требуется действующий **персонифицированный account-auth context** пользователя: cookies/tokens, полученные после подтверждённого входа в Ozon. Account authentication и региональность являются разными контрактами и не должны смешиваться.

Существующий ручной browser/cookies/profile regional workflow сохраняется как fallback/support и не является обязательным условием каждого штатного запуска.

Для Wildberries система получает региональную цену и доступные в используемом endpoint данные об остатке/доступности товара. Для Ozon система получает региональную цену через proxy-first путь, использующий действующую пользовательскую авторизацию.

## 2. User result

Пользователь должен иметь возможность:

1. сформировать список товаров;
2. сформировать список городов и прокси;
3. загрузить оба списка из файла либо БД;
4. один раз предоставить/подтвердить действующую Ozon account-auth сессию, если Ozon включён;
5. запустить парсер;
6. получить результаты для матрицы `Products × Cities × Marketplaces`;
7. повторять цикл по расписанию без ручного переключения городов и без ручного обновления **региональных** cookies/profile для каждого города.

Добавление или изменение товара/города не требует изменения исходного кода.

Если Ozon позже аннулирует/истекает account-auth и реально требует нового подтверждения входа, система должна вернуть явный `OZON_REAUTH_REQUIRED`. Такое повторное подтверждение аккаунта является отдельной credential-maintenance операцией и не считается ручной региональной настройкой, если оно не требуется на каждый город/цикл.

## 3. Input contract

### 3.1 Products

Источник: файл или БД. Сохраняется существующий минимально достаточный товарный контракт.

### 3.2 Cities

Источник: файл или БД.

Минимальная запись города:

```text
city             required
proxy            required
proxy_user       required
proxy_password   required
wb_dest          optional
```

`proxy` — адрес подключения вида `host:port` либо иной поддержанный транспортом эквивалент.

### WB dest rule

Если `wb_dest` задан — использовать его в WB-запросе.

Если `wb_dest` отсутствует — это нормальный допустимый вход. Парсер не требует заполнения `wb_dest`, не считает запись города ошибочной и использует default/региональный контекст WB без принудительного `dest`.

### 3.3 Ozon account authentication

Когда Ozon включён, требуется отдельный глобальный `OzonAuthContext`/credential source, содержащий действующие персонифицированные cookies/tokens подтверждённой пользовательской сессии Ozon.

Это **не поле города** и не отдельный региональный профиль на каждый город.

Обязательные свойства:
- auth cookies/tokens считаются секретами;
- не коммитятся в Git;
- не пишутся в обычные логи, результаты или evidence fixtures;
- штатный Ozon-run никогда не должен тихо переходить в анонимный режим при отсутствии/истечении auth;
- отсутствие/истечение действующей авторизации возвращает `OZON_REAUTH_REQUIRED` либо другой точный auth failure;
- способ безопасного хранения/загрузки credential определяется SG04 без добавления секретов в CityRecord.

Новые обязательные **городские** поля не добавляются без доказанной необходимости.

## 4. Main regional path

### Wildberries

```text
City
  -> Mobile Proxy
  -> WB regional context
  -> WB request
  -> Regional result
```

### Ozon

```text
OzonAuthContext (authenticated user)
  + City
  -> Mobile Proxy / ProxyContext
  -> autonomous Ozon HTTP and/or hidden-browser context
  -> verified requested-city context
  -> authenticated Ozon request
  -> Regional result
```

Штатный повторный путь не должен требовать от пользователя перед каждым циклом:
- открывать браузер;
- выбирать город/ПВЗ;
- обновлять региональные cookies;
- обновлять отдельный региональный профиль;
- вручную создавать региональную сессию.

Начальное подтверждение Ozon account login и редкий re-auth после реального истечения/аннулирования account credential допустимы как credential provisioning/maintenance, но не как per-city/per-cycle workflow.

## 5. Fallback

Существующий ручной browser/cookies/profile regional mechanism не удаляется. Он сохраняется как резервный путь/support capability.

Важно различать:
- **primary `OzonAuthContext`** — обязательная пользовательская авторизация аккаунта;
- **legacy regional profile/cookies workflow** — старый ручной способ одновременно поддерживать авторизацию и региональность через отдельные браузерные профили.

G01 не считается выполненной, если штатный повторный мониторинг всё ещё зависит от ручного обновления региональных cookies/profile для каждого города.

## 6. Marketplace requirements

### Wildberries

Для каждой пары `product × city` получить минимум:

```text
regional price
regional stock / availability
```

Используется минимально достаточная детализация stock/availability, доступная из рабочего WB endpoint; отдельная складская аналитическая подсистема в scope G01 не входит.

### Ozon

Для каждой пары `product × city` получить региональную цену через новый proxy-first authenticated path.

Ozon primary:
- использует действующий пользовательский `OzonAuthContext`;
- может использовать `curl_cffi`, hidden/headless Selenium/Chrome или доказанную комбинацию;
- не требует ручного выбора города/ПВЗ на каждый запуск;
- не принимает анонимную/неавторизованную сессию за штатный путь;
- не смешивает auth validity с city verification.

## 7. Output contract

Для каждого запланированного `marketplace × product × city` система формирует явный результат либо явную ошибку.

Минимальный результат позволяет определить:

```text
timestamp
marketplace
product identifier
city
price
status / error
```

Для Wildberries дополнительно:

```text
stock / availability
```

Ошибка запроса не должна быть неотличима от корректной нулевой доступности или отсутствующего товара.

Для Ozon auth failures (`OZON_REAUTH_REQUIRED`, invalid/expired auth) должны быть отличимы от proxy, region-context, anti-bot и price semantic failures.

## 8. Acceptance criteria

- `G01.A01` — повторный мониторинг без ручного переключения городов;
- `G01.A02` — товары динамически загружаются из файла/БД;
- `G01.A03` — города динамически загружаются из файла/БД;
- `G01.A04` — для **городской региональной конфигурации** достаточен минимальный city/proxy contract; Ozon account auth существует отдельно и глобально;
- `G01.A05` — WB regional price;
- `G01.A06` — WB regional stock/availability;
- `G01.A07` — Ozon regional price через authenticated proxy-first path;
- `G01.A08` — отсутствие `wb_dest` допустимо;
- `G01.A09` — legacy regional cookies/profile fallback сохранён;
- `G01.A10` — ошибки изолированы и не маскируются под реальные значения;
- `G01.A11` — повторный цикл не требует ручной региональной настройки; account re-auth допускается только при фактическом истечении/аннулировании авторизации и не является per-city операцией;
- `G01.A12` — обрабатывается полная заданная матрица `Products × Cities × Marketplaces`;
- `G01.A13` — Ozon personalized auth cookies/tokens используются как секретный account-auth credential, не протекают в Git/log/results/evidence и никогда не заменяются тихим анонимным режимом.

## 9. Automatic FAIL

G01 считается FAIL, если хотя бы одно верно:
- штатная работа требует ручного захода в каждый город или ручного обновления региональных cookies/profile каждого города;
- города, прокси или товары зашиты в код;
- список городов нельзя загрузить тем же принципом, что список товаров;
- WB не возвращает требуемый stock/availability;
- Ozon primary пытается работать без действующей пользовательской account-auth сессии либо тихо переходит в anonymous mode;
- Ozon не работает через основной authenticated proxy-first механизм;
- account-auth cookies/tokens попадают в Git, обычные логи, result rows или committed evidence;
- отсутствие `wb_dest` делает запись города невалидной;
- fallback разрушен;
- результат нельзя однозначно связать с товаром и городом;
- ошибки интерпретируются как реальные цены или нулевые остатки;
- городской пользовательский контракт необоснованно расширен;
- account re-auth фактически требуется отдельно для каждого города/каждого штатного цикла.

## 10. Development / semantic compilation rule

G01 напрямую кодом не реализуется.

Обязательная иерархия:

```text
Goal
  -> Subgoals
  -> Processes
  -> Stages
  -> Tasks
  -> Prompts
```

Каждый элемент каждого уровня имеет:
- Input Contract;
- Output Contract;
- Acceptance Criteria;
- Evidence;
- Failure Conditions.

Родитель считается собранным только если композиция выходных контрактов детей полностью удовлетворяет выходному контракту родителя.

После полной декомпозиции до Prompt-уровня выполняется Semantic / Virtual Compilation всей proposed-generation цепочки. Разработка кода разрешается только после Compilation PASS.
