codeunit 71002 "MTM GT Posted Inv FEL Mgt"
{
    Permissions =
        tabledata "Company Information" = r,
        tabledata Customer = r,
        tabledata "General Ledger Setup" = r,
        tabledata Item = r,
        tabledata "Payment Method" = r,
        tabledata "Payment Terms" = r,
        tabledata "Sales Invoice Header" = rm,
        tabledata "Sales Invoice Line" = r,
        tabledata "Unit of Measure" = r,
        tabledata "VAT Product Posting Group" = r;

    procedure StampPostedInvoiceNoEmail(SalesInv: Record "Sales Invoice Header")
    var
        FacturaGuata: Record "General Ledger Setup";
        Client: HttpClient;
        Request: HttpRequestMessage;
        Response: HttpResponseMessage;
        ContentHeaders: HttpHeaders;
        Content: HttpContent;
        Body: Text;
        RespondeAPI: Text;
        Folio: Text;
        Resultado: Boolean;
        MensajeError: Text;
        UUID: Text;
        XmlCertificado: Text;
        FechaTimbre: Text;
        Serie: Text;
        Numero: Text;
    begin
        FacturaGuata.FindFirst();
        ObtenerFolioVenta(SalesInv."No.", Folio);

        Body := BuildFacturaGTXml(SalesInv);

        Content.WriteFrom(Body);
        Content.GetHeaders(ContentHeaders);
        ContentHeaders.Clear();
        ContentHeaders.Add('Content-Type', 'application/xml');
        ContentHeaders.Add('UsuarioApi', FacturaGuata.UsuarioApi);
        ContentHeaders.Add('LlaveApi', FacturaGuata.LlaveApi);
        ContentHeaders.Add('UsuarioFirma', FacturaGuata.UsuarioFirma);
        ContentHeaders.Add('Identificador', Folio);
        ContentHeaders.Add('LlaveFirma', FacturaGuata.LlaveFirma);

        Request.Content := Content;
        Request.SetRequestUri(FacturaGuata.URLGuatemala + '/fel/procesounificado/transaccion/v2/xml');
        Request.Method := 'POST';

        Client.Send(Request, Response);
        Response.Content().ReadAs(RespondeAPI);

        if Response.HttpStatusCode() = 200 then begin
            ExtractJsonData(false, RespondeAPI, Resultado, MensajeError, UUID, XmlCertificado, FechaTimbre, Serie, Numero);
            ApplyStampResponse(SalesInv, Resultado, MensajeError, UUID, XmlCertificado, FechaTimbre, Serie, Numero);
            exit;
        end;

        ApplyStampResponse(SalesInv, false, CopyStr(RespondeAPI, 1, 2048), '', '', '', '', '');
        Error('No pudo timbrar %1. HTTP %2: %3', SalesInv."No.", Response.HttpStatusCode(), CopyStr(RespondeAPI, 1, 2048));
    end;

    procedure CancelPostedInvoiceWithMotive(SalesInv: Record "Sales Invoice Header"; MotiveText: Text)
    begin
        CancelPostedInvoiceWithMotiveAndIssueDateTime(SalesInv, MotiveText, '');
    end;

    procedure CancelPostedInvoiceWithMotiveAndIssueDateTime(SalesInv: Record "Sales Invoice Header"; MotiveText: Text; IssueDateTimeText: Text)
    var
        FacturaGuata: Record "General Ledger Setup";
        Company: Record "Company Information";
        Cliente: Record Customer;
        Client: HttpClient;
        Request: HttpRequestMessage;
        Response: HttpResponseMessage;
        ContentHeaders: HttpHeaders;
        Content: HttpContent;
        Body: Text;
        RespondeAPI: Text;
        Folio: Text;
        Resultado: Boolean;
        MensajeError: Text;
        UUID: Text;
        XmlCertificado: Text;
        FechaTimbre: Text;
        Serie: Text;
        Numero: Text;
        SalesInvRef: RecordRef;
        FiscalInvoiceNumberPAC: Text;
        DateTimeStamped: Text;
        CancelDateTimeText: Text;
        ResolvedIssueDateTimeText: Text;
    begin
        if MotiveText = '' then
            Error('Cancellation motive text is required.');

        FacturaGuata.FindFirst();
        Company.FindFirst();
        Cliente.Get(SalesInv."Sell-to Customer No.");
        ObtenerFolioVenta(SalesInv."No.", Folio);

        SalesInvRef.GetTable(SalesInv);
        DateTimeStamped := ReadTextField(SalesInvRef, 'Date/Time Stamped');
        FiscalInvoiceNumberPAC := ReadTextField(SalesInvRef, 'Fiscal Invoice Number PAC');
        if DateTimeStamped = '' then
            Error('Invoice %1 does not have Date/Time Stamped.', SalesInv."No.");
        if FiscalInvoiceNumberPAC = '' then
            Error('Invoice %1 does not have Fiscal Invoice Number PAC.', SalesInv."No.");

        CancelDateTimeText := Format(Today(), 0, '<Year4>-<Month,2>-<Day,2>') + 'T' + Format(Time(), 0, '<Hours24,2><Filler Character,0>:<Minutes,2>:<Seconds,2>');
        ResolvedIssueDateTimeText := IssueDateTimeText;
        if ResolvedIssueDateTimeText = '' then
            ResolvedIssueDateTimeText := ResolveCancellationIssueDateTime(DateTimeStamped, SalesInv."Posting Date");

        Body :=
            '<dte:GTAnulacionDocumento xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:dte="http://www.sat.gob.gt/dte/fel/0.1.0" xmlns:n1="http://www.altova.com/samplexml/other-namespace" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Version="0.1" xsi:schemaLocation="http://www.sat.gob.gt/dte/fel/0.1.0 C:\Users\User\Desktop\FEL\Esquemas\GT_AnulacionDocumento-0.1.0.xsd">' +
            '<dte:SAT><dte:AnulacionDTE ID="DatosCertificados">' +
            '<dte:DatosGenerales FechaEmisionDocumentoAnular="' + EscapeXml(ResolvedIssueDateTimeText) + '" FechaHoraAnulacion="' + EscapeXml(CancelDateTimeText) + '" ID="DatosAnulacion" IDReceptor="' + EscapeXml(Cliente."VAT Registration No.") + '" MotivoAnulacion="' + EscapeXml(MotiveText) + '" NITEmisor="' + EscapeXml(Company."VAT Registration No.") + '" NumeroDocumentoAAnular="' + EscapeXml(FiscalInvoiceNumberPAC) + '"></dte:DatosGenerales>' +
            '</dte:AnulacionDTE></dte:SAT></dte:GTAnulacionDocumento>';

        Content.WriteFrom(Body);
        Content.GetHeaders(ContentHeaders);
        ContentHeaders.Clear();
        ContentHeaders.Add('Content-Type', 'application/xml');
        ContentHeaders.Add('UsuarioApi', FacturaGuata.UsuarioApi);
        ContentHeaders.Add('LlaveApi', FacturaGuata.LlaveApi);
        ContentHeaders.Add('UsuarioFirma', FacturaGuata.UsuarioFirma);
        ContentHeaders.Add('Identificador', Folio);
        ContentHeaders.Add('LlaveFirma', FacturaGuata.LlaveFirma);

        Request.Content := Content;
        Request.SetRequestUri(FacturaGuata.URLGuatemala + '/fel/procesounificado/transaccion/v2/xml');
        Request.Method := 'POST';
        Client.Send(Request, Response);
        Response.Content().ReadAs(RespondeAPI);

        if Response.HttpStatusCode() = 200 then begin
            ExtractJsonData(false, RespondeAPI, Resultado, MensajeError, UUID, XmlCertificado, FechaTimbre, Serie, Numero);
            ApplyCancelResponse(SalesInv, Resultado, MensajeError, UUID, XmlCertificado, Serie);
            if not Resultado then
                Error('No pudo cancelar %1 en FEL: %2', SalesInv."No.", MensajeError);
            exit;
        end;

        ApplyCancelResponse(SalesInv, false, CopyStr(RespondeAPI, 1, 2048), '', '', '');
        Error('No pudo cancelar %1 en FEL. HTTP %2: %3', SalesInv."No.", Response.HttpStatusCode(), CopyStr(RespondeAPI, 1, 2048));
    end;

    local procedure BuildFacturaGTXml(SalesInv: Record "Sales Invoice Header"): Text
    var
        Company: Record "Company Information";
        Cliente: Record Customer;
        LineasVenta: Record "Sales Invoice Line";
        ImpuestosinfoSAT: Record "VAT Product Posting Group";
        Body: Text;
        SubBody: Text;
        Otros: Text;
        Subfrase: Text;
        Adendas: Text;
        CurrencyCode: Text;
        TipoEspecial: Text;
        TiempoText: Text;
        FechaText: Text;
        Letras: Text;
        Numeros: Text;
        GranTotal: Decimal;
        GranTotalIVA: Decimal;
        GranTotalT: Text;
        GranTotalIVAT: Text;
        ValidaFrase: Boolean;
        CompanyPais: Text;
        ClientePais: Text;
    begin
        SeparacionAddenda(SalesInv."No.", Letras, Numeros);
        Company.FindFirst();
        Cliente.Get(SalesInv."Sell-to Customer No.");
        CompanyPais := ResolveFelCountryCode(Company.Pais, Company."Country/Region Code", 'company information');
        ClientePais := ResolveFelCountryCode(Cliente.Pais, Cliente."Country/Region Code", StrSubstNo('customer %1', Cliente."No."));

        FechaText := Format(Today(), 0, '<Year4>-<Month,2>-<Day,2>');
        TiempoText := FechaText + 'T' + Format(Time(), 0, '<Hours24,2><Filler Character,0>:<Minutes,2>:<Seconds,2>');

        if SalesInv."Currency Code" = '' then
            CurrencyCode := 'GTQ'
        else
            CurrencyCode := SalesInv."Currency Code";

        LineasVenta.SetRange("Document No.", SalesInv."No.");
        LineasVenta.SetRange(Type, LineasVenta.Type::" ");
        if LineasVenta.FindSet() then
            repeat
                Adendas := LineasVenta.Description;
            until LineasVenta.Next() = 0;

        LineasVenta.Reset();
        LineasVenta.SetRange("Document No.", SalesInv."No.");
        LineasVenta.SetRange(Type, LineasVenta.Type::Item);
        if LineasVenta.FindSet() then
            repeat
                ImpuestosinfoSAT.Get(LineasVenta."VAT Prod. Posting Group");
                if ImpuestosinfoSAT."Codigo Unidad Gravable" = Format(2) then
                    ValidaFrase := true;
            until LineasVenta.Next() = 0;

        if ValidaFrase then
            Subfrase := '<dte:Frase CodigoEscenario="24" TipoFrase="4"/>';

        if Cliente.TipoEspecial then
            TipoEspecial := 'TipoEspecial="CUI"';
        if Cliente.TipoEspecialEXT then
            TipoEspecial := 'TipoEspecial="EXT"';

        Body :=
            '<dte:GTDocumento xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:dte="http://www.sat.gob.gt/dte/fel/0.2.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Version="0.1" xsi:schemaLocation="http://www.sat.gob.gt/dte/fel/0.2.0">' +
            '<dte:SAT ClaseDocumento="dte">' +
            '<dte:DTE ID="DatosCertificados">' +
            '<dte:DatosEmision ID="DatosEmision">' +
            '<dte:DatosGenerales CodigoMoneda="' + EscapeXml(CurrencyCode) + '" FechaHoraEmision="' + EscapeXml(TiempoText) + '" Tipo="FACT"/>' +
            '<dte:Emisor AfiliacionIVA="GEN" CodigoEstablecimiento="1" NITEmisor="' + EscapeXml(Company."VAT Registration No.") + '" NombreComercial="' + EscapeXml(Company."Nombre comercial") + '" NombreEmisor="' + EscapeXml(Company.Name) + '">' +
            '<dte:DireccionEmisor><dte:Direccion>' + EscapeXml(Company.Address) + '</dte:Direccion><dte:CodigoPostal>' + EscapeXml(Company."Post Code") + '</dte:CodigoPostal><dte:Municipio>' + EscapeXml(Company.City) + '</dte:Municipio><dte:Departamento>' + EscapeXml(Company.County) + '</dte:Departamento><dte:Pais>' + EscapeXml(CompanyPais) + '</dte:Pais></dte:DireccionEmisor>' +
            '</dte:Emisor>' +
            '<dte:Receptor CorreoReceptor="' + EscapeXml(Cliente."E-Mail") + '" IDReceptor="' + EscapeXml(Cliente."VAT Registration No.") + '" NombreReceptor="' + EscapeXml(Cliente.Name) + '" ' + TipoEspecial + '>' +
            '<dte:DireccionReceptor><dte:Direccion>' + EscapeXml(Cliente.Address) + '</dte:Direccion><dte:CodigoPostal>' + EscapeXml(Cliente."Post Code") + '</dte:CodigoPostal><dte:Municipio>' + EscapeXml(Cliente.City) + '</dte:Municipio><dte:Departamento>' + EscapeXml(Cliente.County) + '</dte:Departamento><dte:Pais>' + EscapeXml(ClientePais) + '</dte:Pais></dte:DireccionReceptor>' +
            '</dte:Receptor>' +
            '<dte:Frases><dte:Frase CodigoEscenario="1" TipoFrase="1"/>' + Subfrase + '</dte:Frases><dte:Items>';

        SubBody := BuildFacturaGTLineXml(SalesInv, GranTotal, GranTotalIVA, GranTotalT, GranTotalIVAT, ImpuestosinfoSAT);

        Otros :=
            '</dte:Items>' +
            '<dte:Totales><dte:TotalImpuestos><dte:TotalImpuesto NombreCorto="' + EscapeXml(ImpuestosinfoSAT."Nombre Corto -GT") + '" TotalMontoImpuesto="' + GranTotalIVAT + '"/></dte:TotalImpuestos><dte:GranTotal>' + GranTotalT + '</dte:GranTotal></dte:Totales>' +
            '</dte:DatosEmision></dte:DTE>' +
            '<dte:Adenda><Codigo_cliente>' + EscapeXml(Cliente."Codigo Cliente") + '</Codigo_cliente><Observaciones>' + EscapeXml(Adendas) + '</Observaciones><SERIEINTERNA>' + EscapeXml(Letras) + '</SERIEINTERNA><NUMERO-INTERNO>' + EscapeXml(Numeros) + '</NUMERO-INTERNO></dte:Adenda>' +
            '</dte:SAT></dte:GTDocumento>';

        exit(Body + SubBody + Otros);
    end;

    local procedure ResolveFelCountryCode(FelCountryCode: Text; CountryRegionCode: Code[10]; SourceDescription: Text): Text
    var
        ResolvedCountryCode: Text;
    begin
        ResolvedCountryCode := DelChr(FelCountryCode, '=', ' ');
        if ResolvedCountryCode = '' then
            ResolvedCountryCode := DelChr(CountryRegionCode, '=', ' ');

        ResolvedCountryCode := UpperCase(ResolvedCountryCode);
        if ResolvedCountryCode = '' then
            Error('FEL country code is required for %1.', SourceDescription);

        exit(ResolvedCountryCode);
    end;

    local procedure ResolveCancellationIssueDateTime(DateTimeStamped: Text; InvoiceIssueDate: Date): Text
    begin
        if StrLen(DateTimeStamped) < 19 then
            exit(DateTimeStamped);
        if CopyStr(DateTimeStamped, 11, 1) <> 'T' then
            exit(DateTimeStamped);
        if InvoiceIssueDate <> 0D then
            exit(Format(InvoiceIssueDate, 0, '<Year4>-<Month,2>-<Day,2>') + CopyStr(DateTimeStamped, 11, 9));

        exit(CopyStr(DateTimeStamped, 1, 19));
    end;

    local procedure BuildFacturaGTLineXml(SalesInv: Record "Sales Invoice Header"; var GranTotal: Decimal; var GranTotalIVA: Decimal; var GranTotalT: Text; var GranTotalIVAT: Text; var LastImpuestosinfoSAT: Record "VAT Product Posting Group"): Text
    var
        LineasVenta: Record "Sales Invoice Line";
        Producto: Record Item;
        ImpuestosinfoSAT: Record "VAT Product Posting Group";
        SubBody: Text;
        Subimpuestos: Text;
        Subtotal: Decimal;
        TotalIVA: Decimal;
        Total: Decimal;
        SubtotalFactura: Text;
        TotalFactura: Text;
        ImporteTotalIVA: Text;
        PrecioUnitario: Text;
        PrecioTotal: Text;
        NumLine: Integer;
    begin
        LineasVenta.SetRange("Document No.", SalesInv."No.");
        LineasVenta.SetRange(Type, LineasVenta.Type::Item);
        if not LineasVenta.FindSet() then
            exit('');

        repeat
            NumLine += 1;
            Producto.Get(LineasVenta."No.");
            ImpuestosinfoSAT.Get(LineasVenta."VAT Prod. Posting Group");
            LastImpuestosinfoSAT := ImpuestosinfoSAT;

            if LineasVenta."VAT %" > 0 then
                Subtotal := Round(LineasVenta."Amount Including VAT" / 1.12, 0.01, '=')
            else
                Subtotal := LineasVenta."Amount Including VAT";

            Total := LineasVenta."Amount Including VAT";
            TotalIVA := LineasVenta."Amount Including VAT" - Subtotal;
            GranTotal += LineasVenta."Amount Including VAT";
            GranTotalIVA += TotalIVA;

            SubtotalFactura := FormatDecimalNoComma(Subtotal);
            TotalFactura := FormatDecimalNoComma(Total);
            ImporteTotalIVA := FormatDecimalNoComma(TotalIVA);
            GranTotalT := FormatDecimalNoComma(GranTotal);
            GranTotalIVAT := FormatDecimalNoComma(GranTotalIVA);
            PrecioUnitario := FormatDecimalNoComma(LineasVenta."Amount Including VAT" / LineasVenta.Quantity);
            PrecioTotal := FormatDecimalNoComma(LineasVenta."Amount Including VAT");

            Subimpuestos :=
                '<dte:Impuestos><dte:Impuesto><dte:NombreCorto>' + EscapeXml(ImpuestosinfoSAT."Nombre Corto -GT") + '</dte:NombreCorto><dte:CodigoUnidadGravable>' + EscapeXml(ImpuestosinfoSAT."Codigo Unidad Gravable") + '</dte:CodigoUnidadGravable><dte:MontoGravable>' + SubtotalFactura + '</dte:MontoGravable><dte:MontoImpuesto>' + ImporteTotalIVA + '</dte:MontoImpuesto></dte:Impuesto></dte:Impuestos><dte:Total>' + TotalFactura + '</dte:Total></dte:Item>';

            SubBody +=
                '<dte:Item BienOServicio="' + EscapeXml(Producto."Item Category Code") + '" NumeroLinea="' + Format(NumLine) + '">' +
                '<dte:Cantidad>' + FormatDecimalNoComma(LineasVenta.Quantity) + '</dte:Cantidad>' +
                '<dte:UnidadMedida>' + EscapeXml(LineasVenta."Unit of Measure Code") + '</dte:UnidadMedida>' +
                '<dte:Descripcion>' + EscapeXml(GetLineDescription(LineasVenta)) + ' </dte:Descripcion>' +
                '<dte:PrecioUnitario>' + PrecioUnitario + '</dte:PrecioUnitario>' +
                '<dte:Precio>' + PrecioTotal + '</dte:Precio>' +
                '<dte:Descuento>0.00</dte:Descuento>' +
                Subimpuestos;
        until LineasVenta.Next() = 0;

        exit(SubBody);
    end;

    local procedure ApplyStampResponse(SalesInv: Record "Sales Invoice Header"; Resultado: Boolean; MensajeError: Text; UUID: Text; XmlCertificado: Text; FechaTimbre: Text; Serie: Text; Numero: Text)
    var
        Modifica: Record "Sales Invoice Header";
        ModificaRef: RecordRef;
    begin
        Modifica.Get(SalesInv."No.");
        ModificaRef.GetTable(Modifica);

        if Resultado then begin
            WriteTextField(ModificaRef, 'Date/Time Stamped', FechaTimbre);
            WriteTextField(ModificaRef, 'Fiscal Invoice Number PAC', UUID);
            WriteTextField(ModificaRef, 'serie', Serie);
            WriteTextField(ModificaRef, 'numero', Numero);
            WriteBooleanField(ModificaRef, 'Electronic Document Sent', true);
            WriteOptionField(ModificaRef, 'Electronic Document Status', 'Stamp Received');
            WriteTextField(ModificaRef, 'Error Description', '');
            ModificaRef.Modify();
            exit;
        end;

        WriteOptionField(ModificaRef, 'Electronic Document Status', 'Stamp Request Error');
        WriteTextField(ModificaRef, 'Error Description', MensajeError);
        ModificaRef.Modify();
    end;

    local procedure ApplyCancelResponse(SalesInv: Record "Sales Invoice Header"; Resultado: Boolean; MensajeError: Text; UUID: Text; XmlCertificado: Text; Serie: Text)
    var
        Modifica: Record "Sales Invoice Header";
        ModificaRef: RecordRef;
    begin
        Modifica.Get(SalesInv."No.");
        ModificaRef.GetTable(Modifica);

        if Resultado then begin
            WriteTextField(ModificaRef, 'CancelaGTUUID', UUID);
            WriteTextField(ModificaRef, 'serie', Serie);
            WriteBooleanField(ModificaRef, 'Electronic Document Sent', true);
            WriteOptionField(ModificaRef, 'Electronic Document Status', 'Canceled');
            WriteTextField(ModificaRef, 'Error Description', '');
            ModificaRef.Modify();
            exit;
        end;

        WriteOptionField(ModificaRef, 'Electronic Document Status', 'Cancel Error');
        WriteTextField(ModificaRef, 'Error Description', MensajeError);
        ModificaRef.Modify();
    end;

    local procedure ReadTextField(var SourceRef: RecordRef; FieldName: Text): Text
    var
        SourceFieldRef: FieldRef;
    begin
        if not TryFindFieldRef(SourceRef, FieldName, SourceFieldRef) then
            Error('Business Central field %1 is not available on %2.', FieldName, SourceRef.Name());

        exit(Format(SourceFieldRef.Value()));
    end;

    local procedure WriteTextField(var SourceRef: RecordRef; FieldName: Text; Value: Text)
    var
        TargetFieldRef: FieldRef;
    begin
        if not TryFindFieldRef(SourceRef, FieldName, TargetFieldRef) then
            Error('Business Central field %1 is not available on %2.', FieldName, SourceRef.Name());

        TargetFieldRef.Value := CopyStr(Value, 1, TargetFieldRef.Length());
    end;

    local procedure WriteBooleanField(var SourceRef: RecordRef; FieldName: Text; Value: Boolean)
    var
        TargetFieldRef: FieldRef;
    begin
        if not TryFindFieldRef(SourceRef, FieldName, TargetFieldRef) then
            Error('Business Central field %1 is not available on %2.', FieldName, SourceRef.Name());

        TargetFieldRef.Value := Value;
    end;

    local procedure WriteOptionField(var SourceRef: RecordRef; FieldName: Text; Value: Text)
    var
        TargetFieldRef: FieldRef;
    begin
        if not TryFindFieldRef(SourceRef, FieldName, TargetFieldRef) then
            Error('Business Central field %1 is not available on %2.', FieldName, SourceRef.Name());

        Evaluate(TargetFieldRef, Value);
    end;

    local procedure TryFindFieldRef(var SourceRef: RecordRef; FieldName: Text; var TargetFieldRef: FieldRef): Boolean
    var
        FieldIndex: Integer;
        CandidateFieldRef: FieldRef;
    begin
        for FieldIndex := 1 to SourceRef.FieldCount() do begin
            CandidateFieldRef := SourceRef.FieldIndex(FieldIndex);
            if (UpperCase(CandidateFieldRef.Name()) = UpperCase(FieldName)) or
               (UpperCase(CandidateFieldRef.Caption()) = UpperCase(FieldName))
            then begin
                TargetFieldRef := CandidateFieldRef;
                exit(true);
            end;
        end;

        exit(false);
    end;

    local procedure ExtractJsonData(TipoNC: Boolean; JsonResponse: Text; var Resultado: Boolean; var MensajeError: Text; var UUID: Text; var XmlCertificado: Text; var Fecha: Text; var Serie: Text; var Numero: Text)
    var
        JsonObj: JsonObject;
        JsonToken: JsonToken;
        JsonArray: JsonArray;
        ArrayElement: JsonObject;
    begin
        if not JsonObj.ReadFrom(JsonResponse) then
            Error('El texto proporcionado no es un objeto JSON válido.');

        if JsonObj.Get('resultado', JsonToken) then
            Resultado := JsonToken.AsValue().AsBoolean();
        if JsonObj.Get('fecha', JsonToken) then
            Fecha := JsonToken.AsValue().AsText();
        if JsonObj.Get('descripcion_errores', JsonToken) then begin
            JsonArray := JsonToken.AsArray();
            if JsonArray.Get(0, JsonToken) then begin
                ArrayElement := JsonToken.AsObject();
                if ArrayElement.Get('mensaje_error', JsonToken) then
                    MensajeError := JsonToken.AsValue().AsText();
            end;
        end;
        if JsonObj.Get('descripcion', JsonToken) and (MensajeError = '') then
            MensajeError := JsonToken.AsValue().AsText();
        if JsonObj.Get('uuid', JsonToken) then
            UUID := JsonToken.AsValue().AsText();
        if JsonObj.Get('serie', JsonToken) then
            Serie := JsonToken.AsValue().AsText();
        if not TipoNC then
            if JsonObj.Get('numero', JsonToken) then
                Numero := JsonToken.AsValue().AsText();
        if JsonObj.Get('xml_certificado', JsonToken) then
            XmlCertificado := JsonToken.AsValue().AsText();
    end;

    local procedure GetLineDescription(SalesInvoiceLine: Record "Sales Invoice Line"): Text
    begin
        if SalesInvoiceLine."Description XL" <> '' then
            exit(SalesInvoiceLine."Description XL");

        exit(SalesInvoiceLine.Description);
    end;

    local procedure FormatDecimalNoComma(Value: Decimal): Text
    var
        TextValue: Text;
    begin
        TextValue := Format(Value);
        TextValue := DelChr(TextValue, '=', ',');
        exit(TextValue);
    end;

    local procedure ObtenerFolioVenta(NoFactura: Text; var RegresoFolio: Text)
    begin
        RegresoFolio := DelChr(NoFactura, '=', 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz');
    end;

    local procedure SeparacionAddenda(Factura: Text; var Letras: Text; var Numeros: Text)
    begin
        Letras := DelChr(Factura, '=', '0123456789');
        Numeros := DelChr(Factura, '=', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ');
    end;

    local procedure EscapeXml(Value: Text): Text
    begin
        Value := Value.Replace('&', '&amp;');
        Value := Value.Replace('<', '&lt;');
        Value := Value.Replace('>', '&gt;');
        Value := Value.Replace('"', '&quot;');
        Value := Value.Replace('''', '&apos;');
        exit(Value);
    end;
}
